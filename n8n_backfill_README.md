# Workflow n8n one-shot — Backfill `realized_r`

Fichier : [`n8n_backfill_realized_r.workflow.json`](./n8n_backfill_realized_r.workflow.json)

Réinjecte automatiquement `realized_r` dans l'onglet `ANALYSES` du sheet
`gold360_google_sheets` pour les trades clôturés qui n'en ont pas (écart
historique pré-V3). Reproduit exactement la convention de `W2A_V3.0_PARTIAL`.

## Ce qu'il fait

`▶ Run once` → `📋 Read ANALYSES` → `⚙️ Compute realized_r` → `📋 Update realized_r`

- Lit toutes les lignes de `ANALYSES`.
- Garde uniquement `trade_status = closed` **sans** `realized_r`.
- Calcule le R (stopped_out −1 · tp1_hit +0,5·TP1_R · tp2_hit +0,5·TP1_R+0,5·TP2_R · invalidated/expired_no_entry 0).
- Met à jour **uniquement** la colonne `realized_r`, en matchant sur `signal_id`
  (aucune autre colonne touchée).
- Les cas `tp1_hit_expired` / `expired_after_entry` sont ignorés (prix de sortie
  non stocké) — sur ton historique actuel il n'y en a **aucun** parmi les clôturés.

Bilan attendu après exécution : **≈ −11,11 R** sur 52 trades clôturés.

## Import & exécution

1. n8n → **Workflows** → menu **⋮** → **Import from File** → choisir le `.json`.
2. Ouvrir les deux nœuds Google Sheets (`Read` et `Update`) et **re-sélectionner
   ta credential Google Sheets** (les credentials ne sont pas exportés — normal).
3. (Recommandé) Fais une copie du sheet ou note la colonne `realized_r` avant,
   pour pouvoir comparer.
4. Cliquer **Test workflow** (le trigger est manuel — rien ne tourne en auto).
5. Vérifier dans `📋 Update realized_r` le nombre de lignes mises à jour (~47).

## Sécurité / réversibilité

- Le workflow est en **trigger manuel** : il ne s'exécute jamais tout seul.
- Il n'écrit **que** `realized_r`, et seulement sur les lignes `closed` vides.
- `operation: update` (pas append) → aucune ligne créée, aucun doublon.
- Idempotent : relancé, il ignore les lignes déjà remplies.

## Contrôle avant/après (optionnel, en local)

```bash
python3 backfill_realized_r.py gold360.csv   # aperçu des valeurs qui seront écrites
```
