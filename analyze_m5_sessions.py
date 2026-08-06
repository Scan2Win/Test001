#!/usr/bin/env python3
"""
Analyse des sessions sur bougies M5 réelles (onglet GOLD_M5_DATA du sheet
gold360_google_sheets).

Contrairement à `analyze_sessions.py` — qui ne dispose que d'un prix ponctuel
par heure de cron dans l'onglet ANALYSES — ce script travaille sur de vraies
bougies OHLC. Il peut donc tester le modèle de liquidité :

    « L'Asie donne le vrai sens, Londres corrige (balaie le range asiatique),
      puis New York repart dans le sens de l'Asie. »

Usage:
    python3 analyze_m5_sessions.py chemin/vers/gold_m5.csv

Le CSV attend les colonnes : timestamp_utc, open, high, low, close,
tick_volume, session.
"""
import csv
import collections
import statistics
import sys
from datetime import datetime
from math import comb

# Fenêtres en heures UTC : [début, fin[ — alignées sur getSession() de W1,
# l'Asie étant la plage 00h-07h décrite par le trader.
SESSIONS = [
    ("Asie",     0,  8),
    ("Londres",  8, 13),
    ("Overlap", 13, 15),
    ("New York", 15, 21),
]


def num(v):
    v = (v or "").strip().replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def load(path):
    """timestamp -> bougies groupées par jour."""
    days = collections.defaultdict(list)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            ts = (r.get("timestamp_utc") or "").strip()
            if not ts:
                continue
            try:
                t = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                continue
            o, h, l, c = (num(r.get(k)) for k in ("open", "high", "low", "close"))
            if None in (o, h, l, c) or h < l:
                continue
            days[t.date()].append({
                "t": t, "h": t.hour, "o": o, "high": h, "low": l, "c": c,
                "vol": num(r.get("tick_volume")) or 0,
            })
    for d in days:
        days[d].sort(key=lambda x: x["t"])
    return dict(days)


def window(candles, h0, h1):
    return [c for c in candles if h0 <= c["h"] < h1]


def agg(cs):
    if not cs:
        return None
    return {
        "open": cs[0]["o"], "close": cs[-1]["c"],
        "high": max(c["high"] for c in cs), "low": min(c["low"] for c in cs),
        "vol": sum(c["vol"] for c in cs), "n": len(cs),
        "move": cs[-1]["c"] - cs[0]["o"],
        "range": max(c["high"] for c in cs) - min(c["low"] for c in cs),
    }


def sign(x, eps=1e-9):
    return 0 if x is None or abs(x) < eps else (1 if x > 0 else -1)


def binom_p(k, n, p0=0.5):
    """Test binomial bilatéral de k succès sur n, contre une référence p0.

    p0 n'est pas toujours 50 % : pour une séquence de deux conditions la
    référence est 25 %, et pour un test directionnel sur un marché en
    tendance c'est le taux de base observé sur toute la période.
    """
    if n == 0:
        return 1.0
    def pmf(i):
        return comb(n, i) * p0 ** i * (1 - p0) ** (n - i)
    obs = pmf(k)
    return min(1.0, sum(pmf(i) for i in range(n + 1)
                        if pmf(i) <= obs * (1 + 1e-9)))


def line(label, k, n, ref=50.0, width=44):
    if n == 0:
        print(f"{label:<{width}} n/a")
        return
    p = binom_p(k, n, ref / 100.0)
    star = "  ***" if p < 0.01 else ("  *" if p < 0.05 else "")
    print(f"{label:<{width}}{k:>4}/{n:<4} = {100*k/n:5.1f}%  "
          f"(référence {ref:.0f}%, p={p:.3f}){star}")


def main(path):
    days = load(path)
    ds = sorted(days)
    print(f"Bougies M5 : {sum(len(v) for v in days.values())}  |  "
          f"jours : {len(ds)}  |  {ds[0]} → {ds[-1]}\n")

    # Un enregistrement complet par jour
    D = []
    for d in ds:
        cs = days[d]
        rec = {"date": d, "jour": cs[0]["t"].strftime("%a")}
        ok = True
        for name, h0, h1 in SESSIONS:
            a = agg(window(cs, h0, h1))
            rec[name] = a
            if a is None:
                ok = False
        rec["full"] = agg(cs)
        if ok and rec["full"]:
            D.append(rec)
    print(f"Jours complets (4 sessions présentes) : {len(D)}\n")

    # ── 1. Volatilité réelle ────────────────────────────────────────────
    print("=" * 78)
    print("1. VOLATILITÉ RÉELLE PAR SESSION (vraies mèches, pas des clôtures)")
    print("=" * 78)
    print(f"{'Session':<12}{'h':>3}{'range moy':>11}{'$/heure':>9}{'médiane':>10}"
          f"{'p90':>8}{'volume/h':>11}{'|move|':>9}{'move/range':>12}")
    print("-" * 85)
    for name, h0, h1 in SESSIONS + [("JOURNÉE", 0, 21)]:
        if name == "JOURNÉE":
            vals = [r["full"] for r in D]
        else:
            vals = [r[name] for r in D]
        dur = h1 - h0
        rg = sorted(v["range"] for v in vals)
        mv = [abs(v["move"]) for v in vals]
        eff = [abs(v["move"]) / v["range"] for v in vals if v["range"] > 0]
        print(f"{name:<12}{dur:>3}{statistics.mean(rg):>11.2f}"
              f"{statistics.mean(rg)/dur:>9.2f}{statistics.median(rg):>10.2f}"
              f"{rg[int(0.9*(len(rg)-1))]:>8.2f}"
              f"{statistics.mean(v['vol'] for v in vals)/dur:>11.0f}"
              f"{statistics.mean(mv):>9.2f}{statistics.mean(eff):>11.0%}")
    print("→ move/range = efficacité directionnelle : 100 % = la session va tout")
    print("  droit, 20 % = elle fait du yo-yo. C'est ça, une session 'qui tend'.")

    # ── 2. Où naissent les extrêmes du jour ─────────────────────────────
    print()
    print("=" * 78)
    print("2. QUELLE SESSION FABRIQUE LE HAUT ET LE BAS DE LA JOURNÉE ?")
    print("=" * 78)
    hi = collections.Counter()
    lo = collections.Counter()
    for r in D:
        hi[max(SESSIONS, key=lambda s: r[s[0]]["high"])[0]] += 1
        lo[min(SESSIONS, key=lambda s: r[s[0]]["low"])[0]] += 1
    print(f"{'Session':<12}{'fait le HAUT':>16}{'fait le BAS':>16}"
          f"{'fait un extrême':>18}{'par heure':>12}")
    print("-" * 78)
    n = len(D)
    for name, h0, h1 in SESSIONS:
        share = (hi[name] + lo[name]) / (2 * n)
        print(f"{name:<12}{hi[name]:>7} ({100*hi[name]/n:4.1f}%)"
              f"{lo[name]:>7} ({100*lo[name]/n:4.1f}%)"
              f"{hi[name]+lo[name]:>9} ({100*share:4.1f}%)"
              f"{100*share/(h1-h0):>11.1f}%")
    print("→ la session qui pose un extrême est celle qui BORNE la journée ;")
    print("  celle qui n'en pose jamais se contente de voyager entre les deux.")

    # ── 3. Le range asiatique est-il balayé ? ───────────────────────────
    print()
    print("=" * 78)
    print("3. LONDRES BALAIE-T-ELLE LE RANGE ASIATIQUE ? (cœur du modèle)")
    print("=" * 78)
    sw = collections.Counter()
    for r in D:
        a, lo_, hi_ = r["Asie"], None, None
        up = r["Londres"]["high"] > a["high"]
        dn = r["Londres"]["low"] < a["low"]
        sw["haut+bas" if (up and dn) else
           "haut seul" if up else "bas seul" if dn else "aucun"] += 1
    for k in ("haut seul", "bas seul", "haut+bas", "aucun"):
        print(f"  Londres casse le {k:<10} : {sw[k]:>3} jours ({100*sw[k]/n:5.1f}%)")

    # Taux de base : sur la période, la journée clôture au-dessus de la
    # clôture asiatique dans X % des cas. Sur un marché en tendance ce n'est
    # PAS 50 %, et c'est cette référence-là qu'il faut battre.
    base_up = sum(1 for r in D if r["full"]["close"] > r["Asie"]["close"])
    bu = 100.0 * base_up / len(D)
    print()
    print(f"  Taux de base sur la période : clôture du jour > clôture Asie "
          f"dans {bu:.1f}% des cas")
    print("  (c'est CETTE référence que doit battre un balayage, pas 50 %)")
    print()
    print("  ── Après un balayage unilatéral, la journée se retourne-t-elle ? ──")
    for lbl, cond, expect, ref in (
        ("Londres casse le HAUT d'Asie → clôture BAISSIÈRE",
         lambda r: r["Londres"]["high"] > r["Asie"]["high"]
         and not r["Londres"]["low"] < r["Asie"]["low"],
         lambda r: r["full"]["close"] < r["Asie"]["close"], 100.0 - bu),
        ("Londres casse le BAS  d'Asie → clôture HAUSSIÈRE",
         lambda r: r["Londres"]["low"] < r["Asie"]["low"]
         and not r["Londres"]["high"] > r["Asie"]["high"],
         lambda r: r["full"]["close"] > r["Asie"]["close"], bu),
    ):
        sub = [r for r in D if cond(r)]
        line("    " + lbl, sum(1 for r in sub if expect(r)), len(sub), ref=ref)

    # ── 4. Test frontal de l'hypothèse ──────────────────────────────────
    print()
    print("=" * 78)
    print("4. TEST FRONTAL : « Asie = vrai sens, Londres corrige, NY reprend »")
    print("=" * 78)
    a_l = [r for r in D if sign(r["Asie"]["move"]) and sign(r["Londres"]["move"])]
    line("Londres à CONTRE-SENS de l'Asie",
         sum(1 for r in a_l
             if sign(r["Asie"]["move"]) != sign(r["Londres"]["move"])), len(a_l))
    a_n = [r for r in D if sign(r["Asie"]["move"]) and sign(r["New York"]["move"])]
    line("New York DANS LE SENS de l'Asie",
         sum(1 for r in a_n
             if sign(r["Asie"]["move"]) == sign(r["New York"]["move"])), len(a_n))
    a_d = [r for r in D if sign(r["Asie"]["move"])]
    line("Clôture du jour DANS LE SENS de l'Asie",
         sum(1 for r in a_d
             if sign(r["Asie"]["move"]) == sign(r["full"]["close"] - r["Asie"]["close"])),
         len(a_d))
    seq = [r for r in D if sign(r["Asie"]["move"]) and sign(r["Londres"]["move"])
           and sign(r["New York"]["move"])]
    line("SÉQUENCE COMPLÈTE (Asie≠Londres ET Asie=NY)",
         sum(1 for r in seq
             if sign(r["Asie"]["move"]) != sign(r["Londres"]["move"])
             and sign(r["Asie"]["move"]) == sign(r["New York"]["move"])),
         len(seq), ref=25.0)

    # ── 5. Qui prédit quoi ──────────────────────────────────────────────
    print()
    print("=" * 78)
    print("5. CHAQUE SESSION ANNONCE-T-ELLE LA SUITE DE LA JOURNÉE ?")
    print("=" * 78)
    print("   (sens de la session vs sens du mouvement entre sa fin et 20h55 —")
    print("    fenêtres disjointes, donc pas de circularité)")
    for name, _h0, h1 in SESSIONS[:-1]:
        sub = []
        for r in D:
            after = r[name]["close"]
            end = r["full"]["close"]
            if sign(r[name]["move"]) and sign(end - after):
                sub.append((sign(r[name]["move"]), sign(end - after)))
        line(f"  {name} → la suite continue dans son sens",
             sum(1 for a, b in sub if a == b), len(sub))
    print("  → >50 % : la session lance le mouvement. <50 % : elle est corrigée.")

    # ── 6. Biais directionnel brut ──────────────────────────────────────
    print()
    print("=" * 78)
    print("6. BIAIS DIRECTIONNEL DE LA PÉRIODE (contrôle de régime)")
    print("=" * 78)
    for name, _a, _b in SESSIONS:
        mv = [r[name]["move"] for r in D]
        up = sum(1 for x in mv if x > 0)
        print(f"  {name:<10} {up:>3}/{len(mv)} haussiers ({100*up/len(mv):5.1f}%)"
              f"   drift moyen {statistics.mean(mv):+7.2f} $"
              f"   cumul {sum(mv):+9.0f} $")
    tot = [r["full"]["close"] - r["full"]["open"] for r in D]
    print(f"  {'JOURNÉE':<10} {sum(1 for x in tot if x > 0):>3}/{len(tot)} haussiers"
          f" ({100*sum(1 for x in tot if x > 0)/len(tot):5.1f}%)"
          f"   drift moyen {statistics.mean(tot):+7.2f} $"
          f"   cumul {sum(tot):+9.0f} $")
    print("\n  ⚠ Un fort déséquilibre ici signale un marché en tendance sur la")
    print("    période : les taux de réussite ci-dessus en héritent mécaniquement.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
