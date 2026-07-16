# Rapport d'analyse — `gold360_google_sheets`

**Fichier analysé :** journal de signaux de trading sur l'or (GOLD/XAU), généré par
un pipeline automatisé (cron + GPT-5.4), exporté depuis Google Sheets.
**Volume réel :** 53 colonnes × **4 701 lignes de données** (période 20 avril → 15 juillet 2026).
La feuille affiche ~19 000 lignes de grille, mais seules 4 701 contiennent des données.

Analyse effectuée avec le script [`analyze_gold360.py`](./analyze_gold360.py) (parseur CSV
robuste gérant les champs `reasoning` multi-lignes).

---

## 🔴 Problèmes critiques (intégrité des données)

| # | Problème | Détail |
|---|----------|--------|
| 1 | **118 `signal_id` dupliqués, tous divergents** (120 lignes en trop) | Même identifiant, données différentes (timestamp, score, outcome…). La ré-analyse crée une nouvelle ligne au lieu de mettre à jour l'existante. |
| 2 | **904 `duplicate_cron_detected = TRUE` (19,2 %)** | Près d'un signal sur cinq marqué comme exécution de cron dupliquée. **Cause racine probable du n°1.** |
| 3 | **12 lignes corrompues** (≈ lignes 444–504) | `signal_id` + ~50 champs vides ; seuls `outcome=pending` et `trade_status=expired` remplis. Écritures partielles ratées. |

## 🟠 Incohérences logiques

| # | Problème | Détail |
|---|----------|--------|
| 4 | **28 lignes `NO_TRADE` avec `direction`+`entry`+`SL`+`TP` renseignés et `outcome=pending`** | Un trade refusé est quand même suivi comme *live*. Bug du chemin d'écriture. |
| 5 | **13 lignes `sl_hit=TRUE` ET `tp1_hit=TRUE`** | `outcome=tp1_hit`, `realized_r` vide. Double-touche non tranchée ni chiffrée. |
| 6 | **3 TRADE prioritaires (scores 83, 85, 89) avec `alerte_envoyee=FALSE`** | Signaux à forte conviction dont l'alerte n'est jamais partie. |

## 🟡 Comptabilité & complétude

| # | Problème | Détail |
|---|----------|--------|
| 7 | **`realized_r` quasi absent** | 52 trades clôturés, seulement 5 avec R chiffré (13 au total dont 8 sur lignes non clôturées). Bilan de perf impossible. Somme partielle des 13 R = **−2,28 R**. |
| 8 | **2 lignes `outcome=tp1_hit` mais `trade_status=expired`** | État de clôture désynchronisé (devrait être `closed`). |
| 9 | **Traçabilité manquante** | `prompt_version`/`code_version` vides à 99 %, `gpt_raw_output` 98,6 %, `event_sequence` 99,2 %. |
| 10 | **`current_price` vide sur 1 416 lignes (30 %)** | Donnée de marché manquante. |

## 🟢 Format / cosmétique

| # | Problème | Détail |
|---|----------|--------|
| 11 | **Format numérique à virgule décimale française** | `current_price` (3 249), `entry` (181)… Casse tout consommateur attendant le point `.`. |
| 12 | **Feuille non triée chronologiquement** | 1 387 ruptures d'ordre / 4 689 (29,6 %), en partie dues aux doublons. |

---

## ✅ Points sains (vérifiés)

- Aucun prix aberrant (`entry` entre 3 979 et 4 739, cohérent avec l'or).
- **SL et TP toujours du bon côté** vs la direction (0 erreur sur 185 trades).
- `direction` jamais en contradiction avec `proposed_direction`.
- `outcome` toujours cohérent avec les flags `tp1_hit`/`tp2_hit`/`sl_hit`.
- Structure régulière : 100 % des lignes ont 53 colonnes.

---

## 🎯 Priorités recommandées

1. **Corriger le double-déclenchement du cron** → résout n°1, n°2 et une partie du n°12.
2. **Corriger le chemin d'écriture** qui logge des `NO_TRADE` avec niveaux + les lignes orphelines (n°3, n°4).
3. **Fiabiliser le calcul de `realized_r`** et la synchro `trade_status` (n°5, n°7, n°8).
4. **Investiguer les 3 alertes prioritaires non envoyées** (n°6).
