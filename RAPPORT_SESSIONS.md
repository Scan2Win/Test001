# Analyse par session — journal gold360 (XAUUSD)

Source : onglet `ANALYSES` du sheet `gold360_google_sheets`
(`1vxnShmRwFFoAP7j8s6lBGXEZ4930Xneg22kkyZA8Ono`), export du 2026-08-02.
Script reproductible : `analyze_sessions.py`.

**Périmètre** : 5 515 lignes brutes → **834 fenêtres de cron uniques**
(dédoublonnées par `(date, heure UTC)`, cf. `CORRECTIFS_W1.md`),
du **2026-04-20 au 2026-07-31**, soit **73 jours de marché**.

---

## 1. Volume et qualité des opportunités

| Session | Fenêtres | Pré-filtre passé | Score moyen | TRADE | Taux TRADE |
|---|---:|---:|---:|---:|---:|
| Pre-London (06h) | 63 | 28,6 % | 11,7 | 4 | **6,3 %** |
| London (08–12h) | 324 | 28,7 % | 9,1 | 10 | 3,1 % |
| Overlap (13–14h) | 120 | **30,0 %** | **12,0** | 3 | **2,5 %** |
| New York (15–18h) | 257 | 24,5 % | 9,0 | 12 | 4,7 % |
| Cloture NY (20h) | 69 | 24,6 % | 7,1 | 2 | 2,9 % |

**Lecture.** En volume brut, London et New York dominent — mais c'est un
artefact du cron : London a 5 fenêtres par jour, l'Overlap seulement 2. Le
seul indicateur comparable est le **taux de TRADE par fenêtre**.

**Le paradoxe de l'Overlap.** C'est la session avec le **meilleur taux de
pré-filtre (30 %)** et le **meilleur score moyen (12,0)** — et pourtant celle
qui produit **le moins de trades (2,5 %)**. Elle est aussi, de loin, la plus
volatile (§2). Le système détecte donc bien la qualité de cette fenêtre, puis
l'élimine à l'étape suivante.

**Cause probable identifiée dans le code.** Dans `⚙️ Code V4`
(`getSessionBonus`, l.251 et `getExpiryMinutes`, l.243), les tests en cascade
utilisent `.includes()` :

```js
if (sessionName.includes('London'))  return P.london_bonus;   // attrape l'Overlap
if (sessionName.includes('Overlap')) return P.overlap_bonus;  // jamais atteint
```

`'Overlap London/NY'.includes('London')` vaut `true` → l'Overlap reçoit
**+8 au lieu de +10** et un expiry de **180 min au lieu de 120**. Deux points
de score en moins sur la fenêtre la plus active, juste au niveau du seuil
d'exécution. À corriger en testant `Overlap` **avant** `London`.

### Performance : données inexploitables

| Session | TRADE | Entrés | TP1 | SL | realized_r |
|---|---:|---:|---:|---:|---:|
| Pre-London | 4 | 1 | 1 | 0 | vide |
| London | 10 | 2 | 2 | 0 | vide |
| Overlap | 3 | 0 | 0 | 0 | vide |
| New York | 12 | 4 | 2 | 1 | vide |
| Cloture NY | 2 | 0 | 0 | 0 | vide |

**31 TRADE en 73 jours (0,42/jour), dont 7 réellement entrés, et `realized_r`
vide partout.** Aucune conclusion de performance par session n'est possible.
Il faut d'abord exécuter `n8n_backfill_realized_r.workflow.json`, puis
attendre plusieurs mois de trades pour que ce tableau ait un sens.

---

## 2. Amplitude réelle par session

| Session | Durée | Jours | \|move\| moyen | **$/heure** | Médiane | p90 | % haussier | Drift moyen |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Asie (overnight 20h→06h) | 10 h | 62 | 35,50 $ | **3,55** | 28,99 | 71,59 | **32,3 %** | **−8,70 $** |
| Londres (08→12h) | 4 h | 61 | 16,14 $ | 4,03 | 9,77 | 38,80 | 55,7 % | −0,80 $ |
| Overlap (12→14h) | 2 h | 57 | 20,03 $ | **10,02** | 15,92 | 42,41 | 49,1 % | +2,05 $ |
| New York (14→18h) | 4 h | 55 | 20,93 $ | 5,23 | 15,78 | 41,62 | 47,3 % | −3,37 $ |
| Cloture NY (18→20h) | 2 h | 64 | 9,91 $ | 4,96 | 8,04 | 17,84 | 40,6 % | −3,01 $ |
| Journée complète | 24 h | 67 | 51,99 $ | 2,17 | 47,19 | 98,17 | 47,8 % | −10,65 $ |

Deux résultats nets :

1. **L'Overlap 12h–14h est 3× plus volatile que l'Asie à l'heure**
   (10,02 $/h contre 3,55 $/h). L'Asie paraît grosse en valeur absolue
   (35,50 $) uniquement parce que sa fenêtre dure 10 heures. C'est en réalité
   **la session la moins active par unité de temps**.
2. **L'Asie a un biais baissier marqué sur la période** : seulement 32,3 % de
   nuits haussières, −8,70 $ par nuit en moyenne, **−539 $ cumulés**. Sur une
   période où l'or perd 714 $ au total, l'essentiel de la baisse se fait la
   nuit — ce qui est un biais de régime, pas une loi du marché.

---

## 3. Quelle session donne le « vrai sens » ?

### Le test à ne pas faire

Comparer chaque session au mouvement de la **journée entière** donne :
Asie 74,6 %, Londres 76,3 %, Overlap 62,3 %, NY 61,5 %. Ces chiffres sont
**mécaniquement faux** : la journée contient la session testée, et l'Asie pèse
58 % du mouvement absolu total. Une session corrélée à elle-même à 75 %,
ça ne prouve rien.

### Le test correct : la session annonce-t-elle *la suite* de la journée ?

Sens de la session comparé au sens du mouvement entre **sa fin** et 20h UTC —
deux fenêtres disjointes, donc pas de circularité.

| Session | n jours | Continuation | p-value | Verdict |
|---|---:|---:|---:|---|
| Asie (overnight) | 59 | 55,9 % | 0,435 | non significatif |
| Londres | 59 | 55,9 % | 0,435 | non significatif |
| **Overlap** | 54 | **29,6 %** | **0,004** | **significatif — inversé** |
| New York | 50 | 46,0 % | 0,672 | non significatif |

Un seul signal ressort : **ce que fait le marché entre 12h et 14h est défait
dans 70 % des cas entre 14h et la clôture**. La matrice d'accord entre
sessions confirme : Overlap ↔ New York est la case la plus basse du tableau
(**32,1 %** de jours dans le même sens).

### Test direct de ton hypothèse

> *« L'Asie (00h–07h) donne le vrai sens, Londres corrige, l'Amérique reprend
> le vrai sens. »*

| Test | Tous les jours (n=44) | Hors lundi (n=34) | Attendu au hasard |
|---|---:|---:|---:|
| Londres à contre-sens de l'Asie | 45,5 % (p=0,65) | 55,9 % (p=0,61) | 50 % |
| New York dans le sens de l'Asie | 50,0 % (p=1,00) | 44,1 % (p=0,61) | 50 % |
| Séquence complète | 20,5 % | 23,5 % | 25 % |

**L'hypothèse n'est pas vérifiée sur ces données.** Les trois tests sont à la
hauteur du hasard, et la séquence complète tombe même *sous* les 25 % attendus
d'un tirage aléatoire. Aucune p-value n'approche le seuil de significativité.

Ce que dit la donnée à la place : **Londres et l'Overlap poussent ensemble
(63,5 % d'accord — la case la plus haute), et New York défait ce mouvement.**
C'est une phase différente de celle de ton modèle : le point de retournement
est à 14h, pas à l'ouverture de Londres.

### Nuance importante sur ce signal

| Après un Overlap… | n | Move 14h→20h moyen | Médiane |
|---|---:|---:|---:|
| **haussier** | 26 | **−15,52 $** | −14,32 $ |
| baissier | 28 | −0,08 $ | +5,16 $ |

Le « retournement » n'est pas symétrique : **seules les hausses de 12h–14h
sont vendues** ; les baisses ne rebondissent quasiment pas. Et sur une période
où le drift général est de −10,65 $/jour, une partie de cet effet n'est que le
biais baissier du marché.

Stabilité mois par mois : avril 5/8, mai 11/13, **juin 7/15**, juillet 15/18.
Juin casse complètement le pattern. **Ce n'est pas un edge validé, c'est une
piste à backtester** sur données OHLC réelles.

---

## 4. Limites de cette analyse

1. **Pas de données OHLC.** Le journal ne contient que `current_price` aux
   heures de cron (06, 08→18, 20 UTC). On mesure des mouvements point-à-point,
   sans high/low. **C'est la limite bloquante** : ton modèle Asie/Londres/NY
   est un modèle de *liquidité* (Londres balaie le range asiatique, puis NY
   repart), et un balayage de range ne se voit pas dans un écart de clôture à
   clôture. Le test ci-dessus rejette une version *appauvrie* de ton
   hypothèse, pas l'hypothèse elle-même.
2. **La session asiatique n'est jamais loggée** (cron à 06h seulement). Elle
   est approximée par 20h(J−1) → 06h(J), ce qui inclut 4 h de post-clôture US
   et, le lundi, tout le gap du week-end.
3. **Échantillon court** : 73 jours, 34 à 62 jours exploitables par test. À
   cette taille, tout écart inférieur à ~13 points de pourcentage est du bruit.
4. **Un seul actif, un seul régime** : XAUUSD en drift baissier d'avril à
   juillet 2026. Les biais mesurés sont peut-être ceux de la période, pas ceux
   des sessions.
5. **Le prix vient d'un snapshot au moment du cron**, pas d'une bougie fermée.
   Un point aberrant à 14h dégrade à la fois le move Overlap et le move
   suivant, dans des sens opposés.

---

## 5. Ce que je recommande

| # | Action | Pourquoi | Priorité |
|---|---|---|---|
| 1 | **Backfill H1 OHLC** dans un onglet dédié (les nœuds `MetaAPI — H1` récupèrent déjà les bougies, il suffit de les logger) | Sans high/low, on ne peut ni mesurer un range asiatique, ni détecter un balayage — donc pas tester ton modèle | 🔴 |
| 2 | **Corriger le bug Overlap** (`Overlap` testé avant `London` dans les deux fonctions) | Débride la fenêtre la plus volatile du marché (10 $/h), aujourd'hui pénalisée de 2 pts de score | 🔴 |
| 3 | **Exécuter le backfill `realized_r`** | Sans lui, aucune performance par session n'est mesurable | 🟠 |
| 4 | **Ajouter un cron à 02h et 04h UTC** | Fait entrer la session asiatique dans le journal au lieu de l'approximer | 🟠 |
| 5 | Re-tester le fade de l'Overlap après 14h sur 12 mois d'OHLC | Seul signal statistiquement significatif trouvé, mais instable (juin le casse) | 🟡 |

Une fois (1) et (4) en place, le vrai test de ton modèle devient possible :
mesurer le range asiatique 00h–07h, vérifier si Londres en balaie le haut ou
le bas, et si New York clôture du côté annoncé par l'Asie. C'est cette
version-là qu'il faut trancher — pas celle des clôtures horaires.
