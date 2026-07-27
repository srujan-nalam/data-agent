"""Deliberately dirty the warehouse so the agent has realistic mess to handle.

Not applied in Phase 1 (we validate the happy path on clean data first).
Run it once you're ready to prove the agent copes with real-world grime.
Every defect it plants is listed in DEFECTS.md so your eval set has ground
truth.

    python scripts/dirty_data.py
"""
from __future__ import annotations

import argparse
import os

import duckdb

DB_PATH = os.path.join("data", "warehouse.duckdb")


def dirty(path: str) -> None:
    con = duckdb.connect(path)  # writable

    # 1. Duplicate rows (botched-load simulation): re-insert 1% of trips.
    con.execute("INSERT INTO trips SELECT * FROM trips USING SAMPLE 1%;")

    # 2. Nulls in a key column: null out passenger_count for ~2% of rows.
    con.execute(
        "UPDATE trips SET passenger_count = NULL "
        "WHERE random() < 0.02;"
    )

    # 3. Timezone drift: shift 10% of pickups by +5 hours (looks like a
    #    UTC/local mix-up the agent must notice).
    con.execute(
        "UPDATE trips SET pickup_datetime = pickup_datetime + INTERVAL '5 hours' "
        "WHERE random() < 0.10;"
    )

    # 4. Inconsistent categoricals: mixed casing / whitespace in payment_type.
    con.execute(
        "UPDATE trips SET payment_type = ' Card ' "
        "WHERE payment_type = 'card' AND random() < 0.3;"
    )

    total = con.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    con.close()
    print(f"[dirty] mess injected. trips now {total:,} rows. See DEFECTS.md.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=DB_PATH)
    dirty(p.parse_args().db)
