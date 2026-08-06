# Analyse par session — sheet gold360 (XAUUSD)

Source : `gold360_google_sheets`
(`1vxnShmRwFFoAP7j8s6lBGXEZ4930Xneg22kkyZA8Ono`), export du 2026-08-02.
Le fichier contient **7 onglets** ; deux sont utilisés ici :

| Onglet | Lignes | Usage dans ce rapport |
|---|---:|---|
| `ANALYSES` | 6 311 | §1 — opportunités produites par le système |
| `GOLD_M5_DATA` | 16 665 | §2 à §4 — comportement réel du marché (OHLC M5) |
| CALENDAR_NEWS / PERFORMANCE_STATS / W4_RUN_LOG / TUNING_LOG / PARAMETRES_SYSTEME | — | non exploités |

Scripts reproductibles : `analyze_sessions.py` (onglet ANALYSES) et
`analyze_m5_sessions.py` (onglet GOLD_M5_DATA).

---

## 1. Opportunités produites par le système (onglet ANALYSES)

834 fenêtres de cron uniques, 2026-04-20 → 2026-07-31, 73 jours.

| Session | Fenêtres | Pré-filtre | Score moyen | TRADE | Taux TRADE |
|---|---:|---:|---:|---:|---:|
| Pre-London (06h) | 63 | 28,6 % | 11,7 | 4 | **6,3 %** |
| London (08–12h) | 324 | 28,7 % | 9,1 | 10 | 3,1 % |
| Overlap (13–14h) | 120 | **30,0 %** | **12,0** | 3 | **2,5 %** |
| New York (15–18h) | 257 | 24,5 % | 9,0 | 12 | 4,7 % |
| Cloture NY (20h) | 69 | 24,6 % | 7,1 | 2 | 2,9 % |

Le volume brut de London/NY est un artefact du cron (5 fenêtres/jour contre 2
pour l'Overlap). Le seul indicateur comparable est le taux de TRADE par
fenêtre.

**Le paradoxe de l'Overlap** : meilleur pré-filtre (30 %), meilleur score
moyen (12,0), session **de loin la plus volatile** (§2) — et pourtant le taux
de TRADE le plus bas. Cause probable dans `⚙️ Code V4` :

```js
if (sessionName.includes('London'))  return P.london_bonus;   // attrape l'Overlap
if (sessionName.includes('Overlap')) return P.overlap_bonus;  // jamais atteint
```

`'Overlap London/NY'.includes('London')` vaut `true` → l'Overlap reçoit **+8 au
lieu de +10** et expire à **180 min au lieu de 120**. Deux points de score en
moins, pile au niveau du seuil, sur la meilleure fenêtre de la journée.

**Performance : inexploitable.** 31 TRADE en 73 jours, 7 réellement entrés,
`realized_r` vide partout. Lancer `n8n_backfill_realized_r.workflow.json`
avant toute conclusion de performance.

---

## 2. Ce que fait vraiment le marché (bougies M5, 61 jours complets)

2026-05-04 → 2026-07-31. Fenêtres : Asie 00–08h, Londres 08–13h,
Overlap 13–15h, New York 15–21h UTC.

| Session | Durée | Range moyen | **$/heure** | Volume/h | \|move\| | **move/range** |
|---|---:|---:|---:|---:|---:|---:|
| Asie | 8 h | 55,48 $ | 6,94 | 17 372 | 28,97 | 49 % |
| Londres | 5 h | 40,35 $ | 8,07 | 15 077 | 21,44 | 50 % |
| **Overlap** | 2 h | 42,84 $ | **21,42** | **25 699** | 19,03 | 40 % |
| New York | 6 h | 42,89 $ | 7,15 | 15 439 | 23,29 | 47 % |
| Journée | 21 h | 99,88 $ | 4,76 | 17 792 | 51,52 | 48 % |

`move/range` = efficacité directionnelle (distance parcourue / amplitude
balayée). Toutes les sessions sont autour de 40–50 % : **aucune session ne
« tend » nettement plus que les autres**. L'Overlap est la moins efficace
(40 %) tout en étant la plus rapide : beaucoup de mouvement, peu de direction.

**L'Overlap concentre 3× la volatilité horaire de l'Asie** (21,42 $/h contre
6,94 $/h) et 1,5× le volume. L'Asie paraît grosse en absolu (55 $ de range)
uniquement parce qu'elle dure 8 heures.

### Qui borne la journée ?

| Session | Fait le HAUT | Fait le BAS | Un extrême | **Par heure** |
|---|---:|---:|---:|---:|
| **Asie** | **50,8 %** | **50,8 %** | **50,8 %** | 6,4 % |
| Londres | 6,6 % | 1,6 % | **4,1 %** | **0,8 %** |
| Overlap | 19,7 % | 26,2 % | 23,0 % | **11,5 %** |
| New York | 23,0 % | 21,3 % | 22,1 % | 3,7 % |

**Un jour sur deux, le plus haut ET le plus bas de la journée sont posés
pendant la nuit asiatique.** Londres, elle, ne pose pratiquement jamais
d'extrême (4,1 %, soit 0,8 %/heure — vingt fois moins que l'Overlap) : la
séance de Londres se déroule **à l'intérieur des bornes déjà fixées**.

C'est le seul point du modèle qui ressort nettement des données : **l'Asie
cadre la journée.**

---

## 3. Test frontal du modèle

> *« L'Asie (00h–07h) donne le vrai sens, Londres corrige, l'Amérique repart
> dans le vrai sens. »*

### Londres balaie-t-elle le range asiatique ?

| Londres casse… | Jours | % |
|---|---:|---:|
| le haut d'Asie seulement | 17 | 27,9 % |
| le bas d'Asie seulement | 24 | 39,3 % |
| les deux | 1 | 1,6 % |
| aucun (reste dans le range) | 19 | 31,1 % |

**Oui : 69 % des jours, Londres sort du range asiatique.** Mais sortir n'est
pas manipuler. La question est ce qui se passe ensuite.

| Après un balayage unilatéral | Résultat | Taux de base | p |
|---|---:|---:|---:|
| Casse le HAUT d'Asie → clôture baissière | 7/17 = 41,2 % | 57 % | 0,221 |
| Casse le BAS d'Asie → clôture haussière | 6/24 = **25,0 %** | 43 % | 0,099 |

Le taux de base compte : sur la période, le marché clôture au-dessus de la
clôture asiatique dans seulement 42,6 % des cas (marché baissier). Corrigé de
ce biais, **le balayage n'est suivi d'aucun retournement — le mouvement
continue.** Après une cassure du bas asiatique, la journée finit encore plus
bas 3 fois sur 4. C'est une rupture de range, pas un piège à liquidité.

### Les trois affirmations, testées

| Affirmation | Mesure | Référence | p | Verdict |
|---|---:|---:|---:|---|
| Londres à contre-sens de l'Asie | 28/61 = 45,9 % | 50 % | 0,609 | ❌ non |
| New York dans le sens de l'Asie | 28/61 = 45,9 % | 50 % | 0,609 | ❌ non |
| Séquence complète | 14/61 = 23,0 % | 25 % | 0,770 | ❌ non |
| *Clôture du jour dans le sens de l'Asie* | *36/61 = 59,0 %* | *50 %* | *0,200* | ⚠️ tendance, non prouvé |

### Quelle session lance la suite de la journée ?

Sens de la session comparé au mouvement entre **sa fin** et la clôture —
fenêtres disjointes, pas de circularité.

| Session | Continuation | p |
|---|---:|---:|
| **Asie** | **59,0 %** | 0,200 |
| Londres | 45,9 % | 0,609 |
| Overlap | 42,6 % | 0,306 |

**Bilan.** Ton modèle se vérifie sur **un point sur trois** :
l'Asie cadre la journée (elle pose la moitié des extrêmes) et c'est la seule
session dont le sens penche du bon côté pour la suite (59 %) — mais avec
n=61 jours, 59 % n'est pas distinguable du hasard (il faudrait ~63 % pour
atteindre le seuil). Les deux autres affirmations — Londres corrige, New York
reprend — sont contredites : Londres ne corrige pas, elle prolonge autant
qu'elle inverse, et New York part dans le sens de l'Asie moins d'une fois sur
deux.

---

## 4. Régime de la période (contrôle)

| Session | Jours haussiers | Drift moyen | Cumul |
|---|---:|---:|---:|
| Asie | 41,0 % | −4,96 $ | −302 $ |
| Londres | 50,8 % | −0,80 $ | −49 $ |
| Overlap | 42,6 % | −1,43 $ | −87 $ |
| New York | 45,9 % | −4,69 $ | −286 $ |
| **Journée** | **42,6 %** | **−11,12 $** | **−678 $** |

L'or baisse de 678 $ sur la période, et **la baisse se fait surtout la nuit et
en séance US**. Tous les taux ci-dessus héritent de ce biais : les résultats
sont ceux d'un marché baissier de mai à juillet 2026, pas des lois générales
des sessions.

---

## 5. Corrections d'une version précédente de ce rapport

Une première passe n'utilisait que l'onglet `ANALYSES` (un prix ponctuel par
heure de cron, sans mèches). Deux conclusions en sont sorties fausses :

1. **« Pas de données OHLC disponibles »** — faux. L'onglet `GOLD_M5_DATA`
   contient 16 665 bougies M5 complètes. L'export CSV de Google Drive ne
   renvoie que le premier onglet, d'où l'erreur.
2. **« Le mouvement 12h–14h est inversé après 14h dans 70 % des cas
   (p=0,004) »** — artefact. Ce test partageait le prix de 14h entre les deux
   fenêtres mesurées, ce qui crée une corrélation négative artificielle. Sur
   les vraies bougies, la continuation après l'Overlap est de **42,6 %
   (p=0,306)** : rien de significatif.

---

## 6. Limites

1. **61 jours complets.** À cette taille, il faut dépasser ~63 % pour qu'un
   taux se distingue du hasard. Tout ce qui est entre 40 % et 60 % ici est du
   bruit.
2. **Un seul actif, un seul régime** (XAUUSD baissier, mai–juillet 2026).
3. **Les bougies M5 démarrent le 04/05**, l'onglet ANALYSES le 20/04 : les
   deux volets ne couvrent pas exactement la même période.
4. **Le modèle testé est simplifié.** « Balayage » = dépassement du plus haut
   ou du plus bas asiatique. Un vrai test de liquidité regarderait aussi la
   vitesse du rejet, le retour dans le range et le volume au balayage.
5. **Aucun coût de transaction** n'est pris en compte : le spread moyen est
   dans les données mais n'entre dans aucun calcul.

---

## 7. Recommandations

| # | Action | Pourquoi | Priorité |
|---|---|---|---|
| 1 | **Faire tourner W1 pendant l'Asie** (crons 02h et 04h UTC) | L'Asie pose 51 % des extrêmes de la journée et c'est la seule session au tilt directionnel positif — le système ne l'analyse jamais (premier cron à 06h) | 🔴 |
| 2 | **Corriger le bug Overlap** (tester `Overlap` avant `London`) | Débride la fenêtre à 21 $/h et 26 k de volume horaire, aujourd'hui pénalisée de 2 points | 🔴 |
| 3 | **Exécuter le backfill `realized_r`** | Sans lui, aucune performance par session n'est mesurable | 🟠 |
| 4 | **Logger le range asiatique** (`asia_high`, `asia_low`) dans ANALYSES | Permet de relier chaque signal à sa position dans le range de la nuit, et de tester le modèle sur les signaux réels et non plus sur le prix seul | 🟠 |
| 5 | **Rejouer ces tests sur 12 mois** dès que `GOLD_M5_DATA` couvre une année | 61 jours ne suffisent pas à valider un tilt de 59 % | 🟡 |
