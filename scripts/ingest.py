"""Load a dataset into the local DuckDB warehouse.

    python scripts/ingest.py --synthetic          # builds nyc_taxi + ecommerce, offline
    python scripts/ingest.py --ecommerce           # just the e-commerce dataset
    python scripts/ingest.py --real --month 2024-01

--synthetic generates a realistic NYC-yellow-taxi-shaped `trips` table so you
can run the whole agent with no downloads. --real pulls an actual month of
NYC TLC trip data (needs open internet; the file is ~50MB of Parquet).
"""
from __future__ import annotations

import argparse
import os

import duckdb

DB_PATH = os.path.join("data", "warehouse.duckdb")
TLC_URL = (
    "https://d37ci6vzurychx.cloudfront.net/trip-data/"
    "yellow_tripdata_{month}.parquet"
)


def _fresh_connection(path: str) -> duckdb.DuckDBPyConnection:
    # Ingest needs write access, so this is a normal (writable) connection.
    if os.path.exists(path):
        os.remove(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return duckdb.connect(path)


def load_synthetic(path: str, n: int = 50_000) -> None:
    con = _fresh_connection(path)
    con.execute(f"""
        CREATE TABLE trips AS
        SELECT
            (TIMESTAMP '2024-01-01 00:00:00'
                + (random() * 30 * 24 * 3600)::INT * INTERVAL '1 second') AS pickup_datetime,
            (1 + (random() * 5)::INT)                                       AS passenger_count,
            ROUND(0.5 + random() * 18, 2)                                   AS trip_distance,
            ROUND(3 + random() * 60, 2)                                     AS fare_amount,
            ROUND(random() * 15, 2)                                         AS tip_amount,
            (1 + (random() * 262)::INT)                                     AS "PULocationID",
            (1 + (random() * 262)::INT)                                     AS "DOLocationID",
            CASE WHEN random() < 0.7 THEN 'card' ELSE 'cash' END            AS payment_type
        FROM range({n});
    """)
    con.execute("""
        ALTER TABLE trips ADD COLUMN dropoff_datetime TIMESTAMP;
        UPDATE trips SET dropoff_datetime =
            pickup_datetime + (300 + random() * 2400)::INT * INTERVAL '1 second';
        ALTER TABLE trips ADD COLUMN total_amount DOUBLE;
        UPDATE trips SET total_amount = fare_amount + tip_amount;
    """)
    count = con.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    con.close()
    print(f"[ingest] synthetic warehouse ready at {path} ({count:,} trips)")


def load_ecommerce(path: str = "data/ecommerce.duckdb", n: int = 20_000) -> None:
    """A second curated dataset: multi-column e-commerce orders."""
    con = _fresh_connection(path)
    con.execute(f"""
        CREATE TABLE orders AS
        SELECT
            'ORD-' || (row_number() OVER ())::VARCHAR                    AS order_id,
            (1 + (random() * 4000)::INT)                                  AS customer_id,
            (DATE '2024-01-01' + (random() * 180)::INT)                   AS order_date,
            (['Electronics','Home','Toys','Fashion','Grocery','Books'])[1 + (random()*5)::INT] AS category,
            ROUND(5 + random() * 500, 2)                                  AS price,
            (1 + (random() * 4)::INT)                                     AS quantity,
            (['delivered','shipped','cancelled','returned'])[1 + (random()*3)::INT] AS status
        FROM range({n});
    """)
    count = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    con.close()
    print(f"[ingest] e-commerce warehouse ready at {path} ({count:,} orders)")


def load_real(path: str, month: str) -> None:
    con = _fresh_connection(path)
    url = TLC_URL.format(month=month)
    print(f"[ingest] downloading {url} ...")
    con.execute(
        "CREATE TABLE trips AS "
        "SELECT tpep_pickup_datetime AS pickup_datetime, "
        "tpep_dropoff_datetime AS dropoff_datetime, passenger_count, "
        "trip_distance, fare_amount, tip_amount, total_amount, "
        '"PULocationID", "DOLocationID", '
        "payment_type FROM read_parquet(?)",
        [url],
    )
    count = con.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    con.close()
    print(f"[ingest] real warehouse ready at {path} ({count:,} trips)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--synthetic", action="store_true", help="generate offline data (default)")
    p.add_argument("--ecommerce", action="store_true", help="also build the e-commerce dataset")
    p.add_argument("--real", action="store_true", help="download real NYC TLC data")
    p.add_argument("--month", default="2024-01", help="YYYY-MM for --real")
    p.add_argument("--rows", type=int, default=50_000, help="rows for --synthetic")
    p.add_argument("--db", default=DB_PATH)
    args = p.parse_args()

    if args.real:
        load_real(args.db, args.month)
    elif args.ecommerce:
        load_ecommerce()
    else:
        load_synthetic(args.db, args.rows)
        load_ecommerce()
