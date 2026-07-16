# Diagnostic & correctifs `W2_XAUUSD_TECHNIQUE Trade Tracker` (n8n)

Workflow ID : `cImaqGfldsCdkglE` — s'exécute toutes les 3 min, lit `ANALYSES`,
fait tourner une state-machine de suivi de trade, puis met à jour `ANALYSES`
(nœud `📋 Sheets — Update ANALYSES`, `operation: update`, match sur `signal_id`).

Version de code actuelle : `W2A_V3.0_PARTIAL` (déployée le 12 juin 2026).

**Point important :** contrairement à ce que le rapport initial laissait penser,
la plupart des « anomalies » W2 ne sont **pas des bugs actifs** — ce sont des
**écarts historiques** (données figées par une ancienne version). Détail ci-dessous.

---

## Constat 1 — `realized_r` manquant sur 47/52 clôturés → **écart historique, PAS un bug actif**

**Preuve (croisement code_version × realized_r) :**

| code_version | clôturés | avec `realized_r` |
|--------------|----------|-------------------|
| `W2A_V3.0_PARTIAL` | 5 | **5 (100 %)** ✅ |
| `W2A_V2.0` | 22 | 0 |
| (vide, pré-versioning) | 25 | 0 |

`realized_r` a été introduit en **V3 (12 juin)**. La state-machine ne re-traite
jamais un trade déjà `closed` (`if (!['waiting_activation','active'].includes(trade.trade_status)) continue;`)
→ les trades clôturés avant V3 restent **figés sans R**, aucun backfill automatique.
La version actuelle calcule `realized_r` correctement (100 % des trades V3).

### Correctif — backfill unique de l'historique

Le script [`backfill_realized_r.py`](./backfill_realized_r.py) recalcule le R des
52 trades clôturés selon la convention V3. **Tous les 52 sont récupérables** de
façon déterministe (aucun n'est en `tp1_hit_expired`/`expired_after_entry`).

**Bilan réel reconstitué : −11,11 R** (18 gains / 34 pertes).

```
python3 backfill_realized_r.py gold360.csv
# -> émet "signal_id,realized_r" pour chaque ligne à corriger
```

Réinjection : soit collage manuel dans la colonne `realized_r`, soit un petit
workflow n8n one-shot qui lit ces couples et fait un `appendOrUpdate` sur `signal_id`.

---

## Constat 2 — 13 lignes `sl_hit=TRUE` ET `tp1_hit=TRUE` → **comportement CORRECT, pas une contradiction**

C'est le **break-even post-TP1** voulu par la state-machine (lignes ~ `effSL = (tp1_hit && !sl_hit) ? entry : stop_loss`) :
après TP1, le SL est trailé au prix d'entrée. Si le prix revient toucher ce BE,
`sl_hit=TRUE` mais `outcome` reste `tp1_hit` (gain de +0,5 R), ce qui est juste.

Le seul souci est la **traçabilité** : ces 13 lignes ont toutes `event_sequence`
vide (elles sont toutes en V2). Un lecteur voit `sl_hit=TRUE` et croit à une perte.

> **Rien à corriger dans la logique.** V3 résout déjà la lisibilité en écrivant
> `event_sequence = "tp1_partial50 → trail_sl"`. Le backfill (Constat 1) leur
> attribue le bon R positif, ce qui lève l'ambiguïté.

---

## Constat 3 — 12 lignes cassées (`signal_id` vide) → **BUG ACTIF : pas de garde avant l'écriture**

**Cause racine :** la connexion `⚙️ State Machine → 📋 Sheets — Update ANALYSES`
est **directe, sans filtre**. Or la state-machine peut émettre :
- le sentinel `{ no_trades: true, checked_at }` (quand `results` est vide) ;
- des lignes d'erreur `{ signal_id, error, skip: true }` (champs critiques manquants).

Ces items **n'ont pas** de `signal_id` exploitable (ou pas de champs de suivi) et
partent quand même dans `Update ANALYSES`. Avec `operation: update` + match sur un
`signal_id` vide, l'écriture retombe sur une ligne blanche / partielle → les 12
lignes `signal_id` vide, `outcome=pending`, `trade_status=expired`.

### Correctif — intercaler une garde IF/Filter

Entre `⚙️ State Machine — Trade Tracking` et `📋 Sheets — Update ANALYSES`,
ajouter un nœud **Filter** (ou IF) qui ne laisse passer que les vraies mises à jour :

```js
// Filter — garder uniquement les updates valides
{{ $json.skip !== true && $json.no_trades !== true
   && $json.signal_id != null && $json.signal_id !== '' }}
```

Effet : le sentinel et les lignes `skip` sont écartés → plus aucune ligne blanche.

---

## Constat 4 — dépendance à la déduplication de W1 (lien inter-workflow)

`Update ANALYSES` matche sur `signal_id`. Tant que **W1** produit des `signal_id`
dupliqués (voir `CORRECTIFS_W1.md`, correctif 1), n8n ne met à jour qu'**une seule**
des lignes homonymes → l'autre doublon reste `pending` et non suivi.

> Le **correctif W1-1** (`appendOrUpdate` sur `signal_id`) est donc un **prérequis**
> pour que le suivi W2 soit fiable. À appliquer en premier.

---

## Constat 5 — valorisation à l'expiration au prix courant (mineur)

Pour `expired_after_entry` et `tp1_hit_expired`, le R est valorisé avec
`latestClose` = close de la dernière bougie M1 **au moment du traitement**, pas le
prix à l'instant réel d'expiration. Comme W2 tourne toutes les 3 min, l'écart est
faible en régime normal, mais le filet de sécurité 48h peut mal valoriser un trade
traité en retard.

> **Optionnel :** retrouver la bougie M1 dont le `time` correspond à
> `timestamp_analyzed + expiry_minutes` et utiliser son `close` comme prix de sortie.

---

## Récapitulatif

| # | Constat | Nature | Action |
|---|---------|--------|--------|
| 1 | `realized_r` manquant (47/52) | Écart historique | 🔧 Backfill via `backfill_realized_r.py` (**bilan −11,11 R**) |
| 2 | `sl_hit`+`tp1_hit` (13) | Correct (break-even) | ✅ Rien — traçabilité résolue en V3 + backfill |
| 3 | 12 lignes cassées | **Bug actif** | 🔧 Filtre IF avant `Update ANALYSES` |
| 4 | Match sur `signal_id` dupliqué | Dépendance W1 | ⚠️ Appliquer correctif W1-1 d'abord |
| 5 | Valorisation à l'expiration | Mineur | 🔧 (optionnel) close à l'instant d'expiration |
