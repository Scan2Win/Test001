# Correctifs `W1_XAUUSD_TECHNIQUE` (n8n)

Workflow ID : `KDRH2XGWqhozXT2v` — écrit dans l'onglet `ANALYSES` du sheet
`gold360_google_sheets`. Ce document liste les 3 correctifs à appliquer
**manuellement dans n8n** (l'intégration MCP est en lecture seule).

Chaque correctif indique : le nœud, la cause racine, et le changement exact.

---

## Correctif 1 — Doublons de `signal_id` (CRITIQUE)

**Symptôme :** 118 `signal_id` dupliqués (120 lignes en trop) dans le sheet.

**Cause racine (3 facteurs combinés) :**
1. Les nœuds `📋 Sheets — Log V4_True` et `📋 Sheets — Log V4_False` écrivent en
   `operation: append` avec `matchingColumns: []` → ajout aveugle, jamais d'upsert.
2. L'anti-doublon du nœud `⚙️ Code V4` (lignes 571-592) est un *read-then-write*
   avec une race condition (TOCTOU) : deux exécutions concurrentes lisent la
   feuille avant que l'une n'écrive.
3. `signalId` (ligne 528) est à la seconde près → deux exécutions dans la même
   seconde produisent le même ID.

### Action — rendre l'écriture idempotente

Sur **les deux nœuds** `Log V4_True` **et** `Log V4_False` :

| Paramètre | Valeur actuelle | Nouvelle valeur |
|-----------|-----------------|-----------------|
| Operation | `Append` | **`Append or Update`** |
| Column to match on | (vide) | **`signal_id`** |

Effet : un re-run avec le même `signal_id` **met à jour** la ligne au lieu d'en
créer une seconde. Neutralise la conséquence de la race condition et des IDs
à la seconde.

### Renfort optionnel (recommandé) — ID déterministe par fenêtre

Dans `⚙️ Code V4`, remplacer la ligne 528 :

```js
// AVANT (seconde près → non déterministe entre 2 exécutions proches)
const signalId = `GOLD_${now.toISOString().replace(/[^0-9]/g,'').slice(0,14)}_${sessionName.replace(/\s/g,'').toUpperCase()}`;

// APRÈS (arrondi à la fenêtre horaire → 2 crons de la même fenêtre = même ID)
const signalId = `GOLD_${now.toISOString().replace(/[^0-9]/g,'').slice(0,10)}${String(now.getUTCHours()).padStart(2,'0')}00_${sessionName.replace(/\s/g,'').toUpperCase()}`;
```

Combiné à `Append or Update`, deux déclenchements de la même fenêtre horaire
collapsent sur une seule ligne.

---

## Correctif 2 — 904 lignes `duplicate_cron_detected=TRUE` polluent la feuille

**Symptôme :** 19,2 % des lignes sont des doublons cron bloqués mais **quand même écrits**.

**Cause racine :** l'anti-doublon (`⚙️ Code V4`) évite l'appel GPT mais ne
conditionne jamais l'écriture Sheets. `sheets_should_log` reste implicitement vrai.
De plus, le comparatif ne regarde que la **dernière ligne toutes sessions
confondues** (lignes 574-576), pas par session.

### Action A — ne pas logger les doublons cron

Dans `⚙️ Code — No Signal`, avant le `return` final (ligne 186), ajouter :

```js
// Ne pas écrire les doublons cron dans la feuille (bruit)
if (finalPackage.duplicate_cron_detected === true) {
  return [];   // court-circuite Log V4_False → aucune ligne écrite
}
```

> ⚠️ Vérifier que le nœud aval tolère un tableau vide (pas d'écriture). Sinon,
> router via un nœud `IF — duplicate_cron_detected ?` et n'écrire que la branche `false`.

### Action B — comparatif par session (optionnel)

Dans `⚙️ Code V4`, ligne 572, filtrer par session avant de chercher la dernière ligne :

```js
const rowsWithTimestamp = allRows.filter(r =>
  r.timestamp_analyzed && r.session_active === sessionName);
```

---

## Correctif 3 — `NO_TRADE` avec niveaux de prix (28 lignes)

**Symptôme :** 28 lignes `decision=NO_TRADE` mais avec `entry/stop_loss/tp1/tp2`
renseignés et `outcome=pending` → W2 les suit comme des trades live.

**Cause racine :** nœud `Code — Parse GPT-5.4`, lignes 176-177. Quand une
validation échoue, la décision bascule en `NO_TRADE` mais les niveaux GPT
restent recopiés (lignes 213-216). Le flag `trade_fields_coherent` (ligne 164)
est calculé *avant* la bascule, donc il reste `true` à tort.

### Action — purger les niveaux quand la décision devient NO_TRADE

Dans `Code — Parse GPT-5.4`, juste après la ligne 177 (à l'intérieur du bloc
`if (!allValidationsPass && gptAnalysis.decision === 'TRADE')`) :

```js
gptAnalysis.decision = 'NO_TRADE';
// ── FIX : purger les niveaux exécutables pour cohérence ──
gptAnalysis.entry = null;
gptAnalysis.stop_loss = null;
gptAnalysis.tp1 = null;
gptAnalysis.tp2 = null;
gptAnalysis.invalidation = null;
gptAnalysis.entry_anchor_type = null;
gptAnalysis.entry_anchor_price = null;
```

Faire de même dans le bloc de réconciliation `C-NEW` (vers la ligne 315) si une
règle `hard_rule` force `NO_TRADE` : purger les mêmes champs.

---

## Hors périmètre W1

Les **12 lignes cassées** (`signal_id` vide, `outcome=pending`) ne proviennent
pas de W1 (le nœud `No Signal` met un fallback `UNKNOWN_<ts>` et
`outcome=pre_filter_blocked`). Elles sont écrites par **W2 (Trade Tracker)**,
nœud `📋 Sheets — Update ANALYSES`. → à traiter dans le diagnostic de W2, avec
`realized_r` manquant et les double-touches TP1/SL.

---

## Récapitulatif des changements

| # | Nœud | Changement | Priorité |
|---|------|-----------|----------|
| 1 | `Log V4_True` + `Log V4_False` | `append` → `appendOrUpdate` sur `signal_id` | 🔴 Critique |
| 1b | `Code V4` (l.528) | ID déterministe par fenêtre horaire | 🟠 Recommandé |
| 2A | `Code — No Signal` (l.186) | Ne pas logger si `duplicate_cron_detected` | 🟠 |
| 2B | `Code V4` (l.572) | Comparatif anti-doublon par session | 🟡 Optionnel |
| 3 | `Parse GPT-5.4` (l.177 + ~315) | Purger entry/sl/tp quand décision → NO_TRADE | 🟠 |
