#!/usr/bin/env python3
"""
Analyse des sessions de trading (XAUUSD) à partir du journal gold360.

Deux volets :
  A. OPPORTUNITÉS  — combien de setups chaque session produit, et leur qualité
                     (pré-filtre, score, taux de TRADE, issues, realized_r).
  B. DIRECTIONNEL  — quelle session donne le "vrai sens" du marché, en
                     comparant le sens du mouvement de chaque session au sens
                     de la journée complète (test de l'hypothèse
                     Asie = vrai sens / Londres = correction / NY = reprise).

Usage:
    python3 analyze_sessions.py chemin/vers/gold360.csv

Le CSV est l'export de l'onglet ANALYSES du sheet gold360_google_sheets.

Limites connues (voir RAPPORT_SESSIONS.md) :
  - le prix n'est disponible qu'aux heures de cron W1 (06, 08→18, 20 UTC),
    donc les mouvements de session sont mesurés point-à-point, pas en OHLC ;
  - la session asiatique n'est pas loggée : elle est approximée par le
    mouvement overnight 20h(J-1) → 06h(J).
"""
import csv
import collections
import statistics
import sys
from datetime import datetime, timedelta

# Fenêtres de session (heures UTC), telles que définies par getSession()
# dans le nœud "Code V4" du workflow W1_XAUUSD_TECHNIQUE.
SESSION_ORDER = ["Pre-London", "London", "Overlap London/NY", "New York",
                 "Cloture NY", "Hors session"]

# Bornes utilisées pour reconstruire les mouvements de session à partir des
# snapshots de prix. (heure_debut, heure_fin) en UTC + durée en heures.
MOVES = [
    ("Asie (overnight)", 20, 6, 10),   # 20h J-1 -> 06h J (traversée de minuit)
    ("Londres", 8, 12, 4),
    ("Overlap", 12, 14, 2),
    ("New York", 14, 18, 4),
    ("Cloture NY", 18, 20, 2),
]
DUREE = {n: h for n, _a, _b, h in MOVES}
# heure de fin de chaque session, pour mesurer « ce qui se passe après »
FIN = {n: b for n, _a, b, _h in MOVES}


def num(v):
    if v is None:
        return None
    v = v.strip().replace(" ", "").replace(" ", "")
    if not v:
        return None
    # le sheet mélange "4790,66" et "4790.66"
    if "," in v and "." not in v:
        v = v.replace(",", ".")
    else:
        v = v.replace(",", "")
    try:
        return float(v)
    except ValueError:
        return None


def is_true(v):
    return (v or "").strip().upper() == "TRUE"


def parse_ts(v):
    v = (v or "").strip()
    if not v:
        return None
    try:
        return datetime.strptime(v[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def load(path):
    with open(path, newline="") as f:
        rows = [r for r in csv.DictReader(f)
                if any((c or "").strip() for c in r.values())]
    return rows


def dedupe_windows(rows):
    """Une observation par fenêtre de cron (date, heure UTC).

    Le workflow écrit plusieurs lignes pour une même fenêtre (race condition
    + IDs à la seconde, cf. CORRECTIFS_W1.md). On garde la ligne la plus
    récente, qui porte l'état de suivi le plus à jour.
    """
    best = {}
    for r in rows:
        ts = parse_ts(r.get("timestamp_analyzed"))
        if ts is None:
            continue
        key = (ts.date(), ts.hour)
        prev = best.get(key)
        if prev is None or ts > prev[0]:
            best[key] = (ts, r)
    return {k: v[1] for k, v in best.items()}, best


def pct(n, d):
    return f"{100 * n / d:5.1f}%" if d else "    n/a"


# ─────────────────────────────────────────────────────────────────────────
# VOLET A — opportunités par session
# ─────────────────────────────────────────────────────────────────────────
def volet_a(windows):
    by_session = collections.defaultdict(list)
    for r in windows.values():
        by_session[(r.get("session_active") or "?").strip() or "?"].append(r)

    print("=" * 78)
    print("VOLET A — VOLUME ET QUALITÉ DES OPPORTUNITÉS PAR SESSION")
    print("=" * 78)
    print(f"{'Session':<20}{'fenêtres':>9}{'préfiltre':>11}{'score moy':>11}"
          f"{'TRADE':>8}{'taux TRADE':>12}")
    print("-" * 78)

    order = [s for s in SESSION_ORDER if s in by_session]
    order += [s for s in by_session if s not in order]
    for s in order:
        rs = by_session[s]
        pf = sum(1 for r in rs if is_true(r.get("pre_filter_passed")))
        tr = [r for r in rs if (r.get("decision") or "").strip() == "TRADE"]
        scores = [num(r.get("final_score")) for r in rs]
        scores = [x for x in scores if x is not None]
        print(f"{s:<20}{len(rs):>9}{pct(pf, len(rs)):>11}"
              f"{statistics.mean(scores) if scores else 0:>11.1f}"
              f"{len(tr):>8}{pct(len(tr), len(rs)):>12}")

    print()
    print(f"{'Session':<20}{'TRADE':>7}{'entrée':>9}{'TP1':>7}{'TP2':>7}"
          f"{'SL':>7}{'win%':>8}{'R moy':>8}{'R total':>9}")
    print("-" * 78)
    for s in order:
        tr = [r for r in by_session[s]
              if (r.get("decision") or "").strip() == "TRADE"]
        if not tr:
            continue
        touched = [r for r in tr if is_true(r.get("entry_touched"))]
        tp1 = sum(1 for r in touched if is_true(r.get("tp1_hit")))
        tp2 = sum(1 for r in touched if is_true(r.get("tp2_hit")))
        sl = sum(1 for r in touched if is_true(r.get("sl_hit"))
                 and not is_true(r.get("tp1_hit")))
        rr = [num(r.get("realized_r")) for r in tr]
        rr = [x for x in rr if x is not None]
        decided = tp1 + sl
        print(f"{s:<20}{len(tr):>7}{len(touched):>9}{tp1:>7}{tp2:>7}{sl:>7}"
              f"{pct(tp1, decided):>8}"
              f"{statistics.mean(rr) if rr else 0:>8.2f}"
              f"{sum(rr):>9.1f}")
    print("\n(win% = TP1 touché / (TP1 + SL), sur les trades réellement entrés)")


# ─────────────────────────────────────────────────────────────────────────
# VOLET B — quelle session donne le vrai sens
# ─────────────────────────────────────────────────────────────────────────
def build_price_series(windows):
    """(date, heure UTC) -> prix spot relevé par W1."""
    px = {}
    for (d, h), r in windows.items():
        p = num(r.get("current_price"))
        if p and p > 100:
            px[(d, h)] = p
    return px


def session_moves(px):
    """Pour chaque jour : mouvement (en $) de chaque session + de la journée."""
    days = sorted({d for (d, _h) in px})
    out = []
    for d in days:
        prev = None
        # vendredi -> lundi : on remonte jusqu'à 3 jours en arrière
        for back in (1, 2, 3):
            if (d - timedelta(days=back), 20) in px:
                prev = d - timedelta(days=back)
                break
        row = {"date": d, "gap_weekend": prev is not None
               and (d - prev).days > 1}
        for name, h0, h1, _dur in MOVES:
            if name == "Asie (overnight)":
                a = px.get((prev, h0)) if prev else None
                b = px.get((d, h1))
            else:
                a, b = px.get((d, h0)), px.get((d, h1))
            row[name] = (b - a) if (a is not None and b is not None) else None
        a = px.get((prev, 20)) if prev else None
        b = px.get((d, 20))
        row["Journée"] = (b - a) if (a is not None and b is not None) else None
        # journée "cash" : ouverture Londres -> clôture NY
        a, b = px.get((d, 8)), px.get((d, 20))
        row["Journée cash"] = (b - a) if (a is not None and b is not None) else None
        # « suite » de la journée : fin de session -> clôture 20h.
        # Test non biaisé : la session testée n'est PAS incluse dedans.
        for name, _h0, h1, _dur in MOVES:
            a, b = px.get((d, h1)), px.get((d, 20))
            row["apres:" + name] = (b - a) if (a is not None
                                               and b is not None) else None
        out.append(row)
    return out


def sign(x):
    return 0 if x is None or abs(x) < 1e-9 else (1 if x > 0 else -1)


def agreement(moves, a, b):
    pairs = [(m[a], m[b]) for m in moves
             if m.get(a) is not None and m.get(b) is not None]
    pairs = [(x, y) for x, y in pairs if sign(x) and sign(y)]
    if not pairs:
        return 0, 0.0
    same = sum(1 for x, y in pairs if sign(x) == sign(y))
    return len(pairs), 100.0 * same / len(pairs)


def binom_p(k, n):
    """p-value bilatérale d'un test binomial contre p=0.5 (pile ou face)."""
    if n == 0:
        return 1.0
    from math import comb
    d = abs(k - n / 2)
    tot = sum(comb(n, i) for i in range(n + 1)
              if abs(i - n / 2) >= d)
    return min(1.0, tot / 2 ** n)


def volet_b(windows):
    px = build_price_series(windows)
    moves = session_moves(px)
    names = [m[0] for m in MOVES]

    print()
    print("=" * 78)
    print("VOLET B — AMPLITUDE ET DIRECTION PAR SESSION")
    print("=" * 78)
    print(f"{'Session':<20}{'h':>3}{'jours':>7}{'|move| moy':>12}{'$/heure':>9}"
          f"{'médiane':>10}{'p90':>9}{'% haussier':>12}{'drift $':>10}"
          f"{'cumul $':>10}")
    print("-" * 102)
    for n in names + ["Journée", "Journée cash"]:
        vals = [m[n] for m in moves if m.get(n) is not None]
        if not vals:
            continue
        dur = DUREE.get(n, 24 if n == "Journée" else 12)
        a = sorted(abs(v) for v in vals)
        up = sum(1 for v in vals if v > 0)
        print(f"{n:<20}{dur:>3}{len(vals):>7}{statistics.mean(a):>12.2f}"
              f"{statistics.mean(a) / dur:>9.2f}"
              f"{statistics.median(a):>10.2f}"
              f"{a[int(0.9 * (len(a) - 1))]:>9.2f}{pct(up, len(vals)):>12}"
              f"{statistics.mean(vals):>10.2f}{sum(vals):>10.0f}")
    print("→ $/heure = la seule colonne comparable entre sessions "
          "(les fenêtres n'ont pas la même durée).")

    print()
    print("─ TEST BIAISÉ (pour mémoire) : même sens que la journée entière ─")
    print("  ⚠ la session testée est incluse dans le mouvement de la journée,")
    print("    donc ce chiffre est mécaniquement gonflé. Ne pas conclure dessus.")
    for n in names:
        cnt, agr = agreement(moves, n, "Journée")
        print(f"{n:<20}{cnt:>9} jours{agr:>10.1f}%")

    print()
    print("─ TEST NON BIAISÉ : la session annonce-t-elle LA SUITE de la journée ? ─")
    print("  (sens de la session vs sens du mouvement entre sa fin et 20h UTC)")
    print(f"{'Session':<20}{'n jours':>9}{'continuation':>14}{'p-value':>10}")
    print("-" * 78)
    for n in names:
        if FIN[n] >= 20:
            continue
        pairs = [(m[n], m["apres:" + n]) for m in moves
                 if m.get(n) is not None and m.get("apres:" + n) is not None]
        pairs = [(x, y) for x, y in pairs if sign(x) and sign(y)]
        if not pairs:
            continue
        same = sum(1 for x, y in pairs if sign(x) == sign(y))
        p = binom_p(same, len(pairs))
        flag = "  significatif" if p < 0.05 else "  non significatif"
        print(f"{n:<20}{len(pairs):>9}{100 * same / len(pairs):>13.1f}%"
              f"{p:>10.3f}{flag}")
    print("→ >50% = la session prolonge le mouvement ; <50% = elle est corrigée après.")

    print()
    print("─ Détail du signal le plus fort : que fait le marché après l'Overlap ? ─")
    pairs = [(m_["Overlap"], m_["apres:Overlap"]) for m_ in moves
             if m_.get("Overlap") is not None
             and m_.get("apres:Overlap") is not None and sign(m_["Overlap"])]
    for lbl, sub in (("Overlap HAUSSIER", [y for x, y in pairs if x > 0]),
                     ("Overlap BAISSIER", [y for x, y in pairs if x < 0])):
        if sub:
            print(f"  {lbl} (n={len(sub):>2}) → move 14h→20h : "
                  f"moyenne {statistics.mean(sub):+7.2f} $   "
                  f"médiane {statistics.median(sub):+7.2f} $")
    bym = collections.defaultdict(lambda: [0, 0])
    for m_ in moves:
        if (m_.get("Overlap") is None or m_.get("apres:Overlap") is None
                or not sign(m_["Overlap"]) or not sign(m_["apres:Overlap"])):
            continue
        k = m_["date"].strftime("%Y-%m")
        bym[k][1] += 1
        if sign(m_["Overlap"]) != sign(m_["apres:Overlap"]):
            bym[k][0] += 1
    print("  stabilité mois par mois (inversions / jours) : "
          + "  ".join(f"{k}: {v[0]}/{v[1]}" for k, v in sorted(bym.items())))

    print()
    print("─ Matrice d'accord entre sessions (même sens le même jour) ─")
    hdr = "".join(f"{n[:11]:>13}" for n in names)
    print(f"{'':<20}{hdr}")
    for a in names:
        line = f"{a:<20}"
        for b in names:
            if a == b:
                line += f"{'—':>13}"
            else:
                cnt, agr = agreement(moves, a, b)
                line += f"{agr:>12.1f}%"
        print(line)

    print()
    print("─ Test de l'hypothèse Asie → Londres corrige → NY reprend ─")
    for label, sel in (("tous les jours", lambda m: True),
                       ("hors lundi (sans gap week-end)",
                        lambda m: not m["gap_weekend"])):
        seq = [m for m in moves if sel(m)
               and all(m.get(k) is not None and sign(m[k])
                       for k in ("Asie (overnight)", "Londres", "New York"))]
        n = len(seq)
        if not n:
            continue
        asia_lon_opp = sum(1 for m in seq
                           if sign(m["Asie (overnight)"]) != sign(m["Londres"]))
        asia_ny_same = sum(1 for m in seq
                           if sign(m["Asie (overnight)"]) == sign(m["New York"]))
        full = sum(1 for m in seq
                   if sign(m["Asie (overnight)"]) != sign(m["Londres"])
                   and sign(m["Asie (overnight)"]) == sign(m["New York"]))
        print(f"\n  [{label}] jours exploitables : {n}")
        print(f"  Londres à contre-sens de l'Asie           : {asia_lon_opp:>3} "
              f"({100*asia_lon_opp/n:5.1f}%)  hasard 50%  "
              f"p={binom_p(asia_lon_opp, n):.3f}")
        print(f"  New York dans le sens de l'Asie           : {asia_ny_same:>3} "
              f"({100*asia_ny_same/n:5.1f}%)  hasard 50%  "
              f"p={binom_p(asia_ny_same, n):.3f}")
        print(f"  Séquence complète Asie≠Londres ET Asie=NY : {full:>3} "
              f"({100*full/n:5.1f}%)  hasard 25%")

    print()
    print("─ Contribution moyenne au mouvement de la journée ─")
    tot = sum(abs(m["Journée"]) for m in moves if m.get("Journée") is not None)
    for nme in names:
        s = sum(abs(m[nme]) for m in moves
                if m.get(nme) is not None and m.get("Journée") is not None)
        print(f"{nme:<20}{s:>10.0f} $ cumulés  ({pct(s, tot) if tot else 'n/a'} "
              f"du mouvement absolu total)")
    return moves


def main(path):
    rows = load(path)
    windows, _ = dedupe_windows(rows)
    print(f"Lignes brutes : {len(rows)}  →  fenêtres uniques : {len(windows)}")
    days = sorted({d for (d, _h) in windows})
    print(f"Période : {days[0]} → {days[-1]}  ({len(days)} jours de marché)\n")
    volet_a(windows)
    volet_b(windows)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
