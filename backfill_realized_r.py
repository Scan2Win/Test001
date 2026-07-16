#!/usr/bin/env python3
"""
Backfill de `realized_r` pour les trades clôturés historiques du sheet gold360.

Contexte : `realized_r` n'a été introduit que dans W2A_V3.0_PARTIAL (12 juin 2026).
Les trades clôturés avant cette version n'ont pas de R, et la state-machine de W2
ne re-traite jamais un trade déjà `closed` → aucun backfill automatique.

Ce script recalcule `realized_r` selon la MÊME convention que W2 V3 :
    R = |entry - stop_loss|
    stopped_out            -> -1.0
    invalidated            ->  0
    expired_no_entry       ->  0
    tp1_hit                -> +0.5 * TP1_R          (moitié TP1, runner au break-even)
    tp2_hit                -> +0.5 * TP1_R + 0.5 * TP2_R
    tp1_hit_expired        -> +0.5 * TP1_R + 0.5 * runner@close   (exit price requis)
    expired_after_entry    -> position pleine @ close             (exit price requis)

Les deux derniers cas nécessitent le prix de sortie réel (non stocké dans
l'historique) : ils sont laissés à None (à valoriser manuellement si besoin).

Usage:
    python3 backfill_realized_r.py chemin/vers/gold360.csv
Sortie : liste signal_id -> realized_r à réinjecter, + bilan agrégé.
"""
import csv
import sys


def num(v):
    try:
        return float(v.replace(",", ".").strip())
    except (ValueError, AttributeError):
        return None


def compute_realized_r(outcome, entry, stop_loss, tp1, tp2):
    """Retourne le R réalisé, ou None si non déterministe sans prix de sortie."""
    if entry is None or stop_loss is None:
        return None
    risk = abs(entry - stop_loss)
    if risk == 0:
        return None
    tp1_r = abs(tp1 - entry) / risk if tp1 is not None else 0
    tp2_r = abs(tp2 - entry) / risk if tp2 is not None else 0
    table = {
        "stopped_out": -1.0,
        "invalidated": 0.0,
        "expired_no_entry": 0.0,
        "tp1_hit": 0.5 * tp1_r,
        "tp2_hit": 0.5 * tp1_r + 0.5 * tp2_r,
    }
    # tp1_hit_expired / expired_after_entry : exit price inconnu -> None
    return table.get(outcome)


def main(path):
    rows = []
    with open(path, newline="") as f:
        r = csv.reader(f)
        header = next(r)
        for row in r:
            if all(c.strip() == "" for c in row):
                continue
            rows.append(dict(zip(header, row)))

    closed = [r for r in rows if r["trade_status"].strip() == "closed"]
    to_fill, undecidable, filled_vals = [], [], []

    for r in closed:
        if r["realized_r"].strip():
            continue  # déjà renseigné
        val = compute_realized_r(
            r["outcome"].strip(),
            num(r["entry"]), num(r["stop_loss"]),
            num(r["tp1"]), num(r["tp2"]),
        )
        if val is None:
            undecidable.append(r["signal_id"])
        else:
            to_fill.append((r["signal_id"], round(val, 3)))
            filled_vals.append(val)

    print(f"Trades clôturés            : {len(closed)}")
    print(f"realized_r déjà présent    : {sum(1 for r in closed if r['realized_r'].strip())}")
    print(f"À backfiller (déterministe): {len(to_fill)}")
    print(f"Non décidable (exit price) : {len(undecidable)}")
    if filled_vals:
        wins = sum(1 for v in filled_vals if v > 0)
        losses = sum(1 for v in filled_vals if v < 0)
        print(f"\nBilan backfillé : {round(sum(filled_vals), 2)} R "
              f"({wins} gains / {losses} pertes)")
    print("\n--- signal_id -> realized_r (à réinjecter) ---")
    for sid, val in to_fill:
        print(f"{sid},{val}")
    if undecidable:
        print("\n--- non décidables (renseigner exit price à la main) ---")
        for sid in undecidable:
            print(sid)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
