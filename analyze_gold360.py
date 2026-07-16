#!/usr/bin/env python3
"""
Analyse d'intégrité du journal de signaux gold360 (export CSV du Google Sheet).

Usage:
    python3 analyze_gold360.py chemin/vers/gold360.csv

Le script détecte les problèmes d'intégrité et de cohérence logique décrits
dans RAPPORT_ANALYSE.md (doublons, lignes cassées, incohérences TP/SL,
NO_TRADE avec niveaux, format numérique, etc.).
"""
import csv
import collections
import sys


def load(path):
    rows = []
    with open(path, newline="") as f:
        r = csv.reader(f)
        header = next(r)
        for row in r:
            if all(c.strip() == "" for c in row):
                continue
            rows.append(dict(zip(header, row)))
    return header, rows


def is_true(v):
    return v.strip().upper() == "TRUE"


def filled(v):
    return v.strip() != ""


def num(v):
    try:
        return float(v.replace(",", ".").strip())
    except ValueError:
        return None


def main(path):
    header, rows = load(path)
    n = len(rows)
    print(f"Colonnes: {len(header)} | Lignes de données: {n}\n")

    # 1. Doublons de signal_id
    ids = collections.defaultdict(list)
    for r in rows:
        if filled(r["signal_id"]):
            ids[r["signal_id"]].append(r)
    dups = {k: v for k, v in ids.items() if len(v) > 1}
    divergent = sum(
        1 for v in dups.values()
        if len({tuple(r[c] for c in header) for r in v}) > 1
    )
    print(f"[CRITIQUE] signal_id dupliqués: {len(dups)} "
          f"(dont {divergent} avec données divergentes)")

    # 2. Cron dupliqué
    dcron = sum(1 for r in rows if is_true(r["duplicate_cron_detected"]))
    print(f"[CRITIQUE] duplicate_cron_detected=TRUE: {dcron} ({100*dcron/n:.1f}%)")

    # 3. Lignes cassées (signal_id vide)
    broken = [i for i, r in enumerate(rows) if not filled(r["signal_id"])]
    print(f"[CRITIQUE] lignes cassées (signal_id vide): {len(broken)}")

    # 4. NO_TRADE avec niveaux renseignés
    no_trade_lvl = sum(
        1 for r in rows
        if r["decision"].strip() == "NO_TRADE" and filled(r["entry"])
    )
    print(f"[HAUT] NO_TRADE avec entry/SL/TP renseignés: {no_trade_lvl}")

    # 5. Double-touche TP1 + SL
    tp_and_sl = sum(1 for r in rows if is_true(r["sl_hit"]) and is_true(r["tp1_hit"]))
    print(f"[HAUT] sl_hit=TRUE ET tp1_hit=TRUE (double-touche): {tp_and_sl}")

    # 6. TRADE prioritaire sans alerte
    no_alert = [
        r for r in rows
        if r["decision"].strip() == "TRADE" and not is_true(r["alerte_envoyee"])
    ]
    print(f"[HAUT] TRADE sans alerte envoyée: {len(no_alert)}")

    # 7. realized_r manquant sur trades clôturés
    closed = [r for r in rows if r["trade_status"].strip() == "closed"]
    closed_rr = sum(1 for r in closed if filled(r["realized_r"]))
    print(f"[MOYEN] trades closed: {len(closed)} | avec realized_r: {closed_rr}")

    # 8. Statut de clôture désynchronisé
    desync = sum(
        1 for r in rows
        if r["outcome"] in ("tp1_hit", "tp2_hit", "stopped_out")
        and r["trade_status"].strip() != "closed"
    )
    print(f"[MOYEN] outcome gagnant/perdant mais trade_status != closed: {desync}")

    # 9. current_price manquant
    no_price = sum(1 for r in rows if not filled(r["current_price"]))
    print(f"[MOYEN] current_price vide: {no_price} ({100*no_price/n:.1f}%)")

    # 10. Format virgule décimale
    comma = sum(1 for r in rows if "," in r["current_price"])
    print(f"[BAS] current_price en virgule décimale: {comma}")

    # Contrôles de non-régression (doivent rester à 0)
    bad_side = 0
    for r in rows:
        e, sl, d = num(r["entry"]), num(r["stop_loss"]), r["direction"].strip()
        if e and sl and d:
            if (d == "BUY" and sl >= e) or (d == "SELL" and sl <= e):
                bad_side += 1
    print(f"\n[OK attendu=0] SL du mauvais côté vs direction: {bad_side}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
