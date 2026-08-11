# Diagnostic & correctifs `W4 — Gold M5 Data Collector` (n8n)

Workflow ID : `lkyM0P79s0kgnfWE` — collecte les bougies M5 de l'or (MetaAPI) et
les écrit dans l'onglet `GOLD_M5_DATA`. Journalise chaque run dans `W4_RUN_LOG`.

**Appréciation générale : c'est le workflow le mieux conçu des trois.**
Déduplication par `timestamp_utc`, détection de gap qui distingue correctement le
week-end et la pause settlement quotidienne XM (21:00–22:00 UTC), retry sur l'appel
MetaAPI (3 essais), journal de run structuré. Les points ci-dessous sont des
failles ciblées, pas une refonte.

---

## 🔴 1. La panne totale de données est SILENCIEUSE (critique)

**Symptôme potentiel :** si MetaAPI ne renvoie rien (0 bougie) ou tronque la
réponse, **aucune alerte Telegram n'est envoyée**.

**Cause racine :** la sortie de `⚙️ Process & Dedup` part vers 3 nœuds, mais
l'alerte Telegram n'est branchée que sur `🔀 IF — gap_detected?`. Or :
- `status = WARN_NO_DATA` (0 bougie reçue) → `gap_detected` reste `false`
- `status = WARN_LIMIT_HIT` (réponse tronquée) → `gap_detected` reste `false`

Résultat : **la pire panne (aucune donnée) est justement celle qui n'alerte pas.**
Elle n'est écrite que dans `W4_RUN_LOG`, que personne ne surveille en temps réel.
Conséquence en cascade : W1 analyse alors sur des prix périmés sans le savoir.

### Correctif — alerter aussi sur `WARN_NO_DATA` / `WARN_LIMIT_HIT`

Modifier la condition du nœud `🔀 IF — gap_detected?` (ou ajouter une 2ᵉ branche)
pour déclencher l'alerte dès qu'un statut anormal apparaît :

```js
// Condition d'alerte élargie
{{ $json.gap_detected === true
   || $json.run_log.status === 'WARN_NO_DATA'
   || $json.run_log.status === 'WARN_LIMIT_HIT' }}
```

Adapter le message Telegram pour afficher `run_log.status` en tête.

---

## 🟠 2. Le « backfill » ne peut pas remonter au-delà de ~1000 bougies (~3-4 jours)

**Symptôme :** le run `backfill` annonce `window_start = 2026-05-04`, mais ne
récupère en réalité que les **1000 dernières bougies** M5.

**Cause racine :** `⚙️ Compute Window` fixe `fetch_limit = 1000` pour le backfill,
et l'appel MetaAPI ne fait que `?limit=1000` (les **1000 dernières** bougies, pas
une plage). `⚙️ Process & Dedup` filtre ensuite sur `[window_start, window_end]`,
mais si la fenêtre couvre des mois, on ne dispose déjà que des ~3-4 derniers jours.

1000 bougies M5 ≈ 1000 × 5 min ≈ **3,5 jours de marché continu**. Impossible de
backfiller depuis mai. Le statut passe bien `WARN_LIMIT_HIT` (bon réflexe), mais
le backfill **sous-livre en silence**.

### Correctif — paginer par plage temporelle

L'API MetaAPI accepte une borne de fin (`startTime`/`endTime` selon la version).
Remplacer l'appel unique par une **boucle de pagination** : récupérer 1000 bougies,
prendre la plus ancienne, redemander avant cette date, jusqu'à atteindre
`window_start`. À défaut, documenter que le backfill = « ~4 derniers jours
seulement » et le lancer plusieurs fois.

---

## 🟠 3. Un échec de lecture peut injecter des doublons en masse

**Cause racine :** le nœud `📋 Read GOLD_M5_DATA` a `alwaysOutputData: true`. Si la
lecture échoue ou renvoie vide (hoquet API), `existingItems` est vide →
`existingTimestamps` est vide → **toutes** les bougies de la fenêtre sont vues comme
« nouvelles » → `📋 Append GOLD_M5_DATA` (opération `append`, pas d'upsert) les
ré-insère. Sur un run daily, jusqu'à ~360 doublons d'un coup.

La déduplication repose **entièrement** sur ce snapshot en mémoire ; l'écriture au
niveau feuille n'a aucun garde-fou.

### Correctif — garde anti-injection

Dans `⚙️ Process & Dedup`, avant de valider l'append, vérifier la cohérence du
snapshot lu :

```js
// Garde : si la feuille devrait contenir des données mais le read est vide,
// on suspecte un échec de lecture -> ne rien insérer ce run.
const existingCount = existingItems.filter(r => r.json && r.json.timestamp_utc).length;
if (existingCount === 0 && meta.run_type !== 'backfill') {
  return [{ json: {
    has_new_candles: false, gap_detected: false, gap_details: '',
    run_log: { ...run_log, status: 'WARN_EMPTY_READ', candles_inserted: 0 },
    candles_to_append: []
  }}];
}
```

(et faire remonter `WARN_EMPTY_READ` dans l'alerte du correctif 1).

---

## 🟡 4. Lecture intégrale de la feuille à chaque run (scalabilité)

`Read GOLD_M5_DATA` lit **toute** la feuille à chaque exécution pour construire le
set de dédup. À ~288 bougies M5/jour, la feuille grossit vite ; la lecture et le
`Set` deviennent lents et coûteux en quota API sur plusieurs mois.

> **Piste :** ne relire qu'une fenêtre récente (par ex. les N dernières lignes via
> un range), suffisante puisque la fenêtre de collecte ne dépasse jamais 83h.

## 🟡 5. `append` + runs concurrents (mineur)

Le backfill manuel lancé pendant que le trigger daily tourne = deux runs qui lisent
le même snapshot puis appendent → doublons possibles. Probabilité faible (triggers
espacés), mais réelle. Le correctif 3 (garde) et un passage éventuel en
`appendOrUpdate` sur `timestamp_utc` l'élimineraient.

---

## Récapitulatif

| # | Constat | Gravité | Correctif |
|---|---------|---------|-----------|
| 1 | Panne totale (0 bougie) sans alerte | 🔴 Critique | Élargir la condition d'alerte à `WARN_NO_DATA`/`WARN_LIMIT_HIT` |
| 2 | Backfill plafonné à ~1000 bougies | 🟠 | Paginer par plage temporelle |
| 3 | Read vide → flot de doublons | 🟠 | Garde anti-injection sur snapshot vide |
| 4 | Lecture intégrale à chaque run | 🟡 | Relire une fenêtre récente seulement |
| 5 | `append` + runs concurrents | 🟡 | Garde (corr. 3) + `appendOrUpdate` sur `timestamp_utc` |

## Validation empirique (proposée)

Ces constats viennent de la lecture du code. Pour les **confirmer sur données
réelles**, je peux analyser les onglets `GOLD_M5_DATA` (doublons de `timestamp_utc`,
trous horaires réels) et `W4_RUN_LOG` (historique des statuts `WARN_*`).
