"""Dataset registry: maps a dataset_id to a warehouse, and ingests uploads.

Curated datasets ship with the app; users can also upload a CSV, which is
loaded into its own read-only DuckDB file and registered at runtime. This is
what lets the same agent answer questions over whatever it's pointed at —
schema discovery does the rest.
"""
from __future__ import annotations

import json
import os
import re

import duckdb

from data.warehouse import Warehouse

DATA_DIR = "data"
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
REGISTRY_FILE = os.path.join(DATA_DIR, "datasets.json")

# Curated datasets. Uploaded ones are appended to the JSON registry.
_CURATED = {
    "nyc_taxi": {"label": "NYC Taxi Trips", "path": os.path.join(DATA_DIR, "warehouse.duckdb")},
    "ecommerce": {"label": "E-commerce Orders", "path": os.path.join(DATA_DIR, "ecommerce.duckdb")},
}

_warehouses: dict[str, Warehouse] = {}


def _load_registry() -> dict:
    reg = dict(_CURATED)
    if os.path.exists(REGISTRY_FILE):
        try:
            reg.update(json.load(open(REGISTRY_FILE)))
        except Exception:
            pass
    return reg


def list_datasets() -> list[dict]:
    reg = _load_registry()
    return [
        {"id": ds_id, "label": meta["label"]}
        for ds_id, meta in reg.items()
        if os.path.exists(meta["path"])
    ]


def get_warehouse(dataset_id: str) -> Warehouse:
    if dataset_id in _warehouses:
        return _warehouses[dataset_id]
    reg = _load_registry()
    if dataset_id not in reg:
        raise KeyError(f"unknown dataset '{dataset_id}'")
    wh = Warehouse(reg[dataset_id]["path"])
    _warehouses[dataset_id] = wh
    return wh


def register_upload(filename: str, csv_path: str) -> dict:
    """Load a CSV into a fresh read-only DuckDB and register it."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ds_id = "upload_" + re.sub(r"[^a-z0-9]+", "_", os.path.splitext(filename)[0].lower())[:40]
    db_path = os.path.join(UPLOAD_DIR, ds_id + ".duckdb")
    if os.path.exists(db_path):
        os.remove(db_path)

    con = duckdb.connect(db_path)  # writable for ingest
    is_parquet = csv_path.lower().endswith(".parquet") or filename.lower().endswith(".parquet")
    reader = "read_parquet(?)" if is_parquet else "read_csv_auto(?, sample_size=-1)"
    con.execute(f"CREATE TABLE data AS SELECT * FROM {reader}", [csv_path])
    n = con.execute("SELECT COUNT(*) FROM data").fetchone()[0]
    con.close()

    reg = {}
    if os.path.exists(REGISTRY_FILE):
        try:
            reg = json.load(open(REGISTRY_FILE))
        except Exception:
            reg = {}
    reg[ds_id] = {"label": filename, "path": db_path}
    json.dump(reg, open(REGISTRY_FILE, "w"), indent=2)
    _warehouses.pop(ds_id, None)  # force reopen read-only
    return {"id": ds_id, "label": filename, "rows": n}


def register_url(url: str, name: str | None = None, max_bytes: int = 60_000_000) -> dict:
    """Download a public CSV/Parquet by URL and register it as a dataset.

    Only http(s) is allowed, and obvious internal hosts are blocked (basic SSRF
    guard). The file is streamed to a temp path with a size cap, then loaded via
    register_upload (which discovers the schema).
    """
    import ipaddress
    import socket
    import tempfile
    import urllib.parse
    import urllib.request

    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    host = urllib.parse.urlparse(url).hostname or ""
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "metadata.google.internal"):
        raise ValueError("that host isn't allowed")
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(host))
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError("private/internal hosts aren't allowed")
    except (socket.gaierror, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise

    fname = name or os.path.basename(urllib.parse.urlparse(url).path) or "remote.csv"
    if not os.path.splitext(fname)[1]:
        fname += ".csv"
    suffix = os.path.splitext(fname)[1]

    req = urllib.request.Request(url, headers={"User-Agent": "data-agent/1.0"})
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        with urllib.request.urlopen(req, timeout=30) as resp:
            written = 0
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError(f"file exceeds {max_bytes // 1_000_000} MB limit")
                tmp.write(chunk)
    try:
        return register_upload(fname, tmp_path)
    finally:
        os.unlink(tmp_path)


_NUMERIC = ("INT", "DOUBLE", "FLOAT", "DECIMAL", "REAL", "NUMERIC", "HUGEINT")


def _pretty(col: str) -> str:
    return col.replace("_", " ").strip().lower()


def suggest_questions(dataset_id: str) -> list[str]:
    """Deterministic example questions derived from a dataset's schema.
    No LLM call, so it's free to run on every dataset switch."""
    schema = get_warehouse(dataset_id).schema()
    if not schema:
        return ["How many rows are there?"]
    table, cols = next(iter(schema.items()))

    def is_id(c: str) -> bool:
        c = c.lower()
        return c == "id" or c.endswith("_id") or c.endswith("id")

    numeric = [c for c, t in cols if any(k in t.upper() for k in _NUMERIC)]
    numeric = [c for c in numeric if not is_id(c)] or numeric
    categorical = [c for c, t in cols if "CHAR" in t.upper() or t.upper() == "TEXT"]
    categorical = [c for c in categorical if not is_id(c)] or categorical
    dated = [c for c, t in cols if "DATE" in t.upper() or "TIMESTAMP" in t.upper()]

    def prefer(nums):
        for kw in ("amount", "price", "fare", "total", "revenue", "tip", "distance",
                   "value", "age", "score", "rate", "temp", "precip", "wind", "count"):
            for c in nums:
                if kw in c.lower():
                    return c
        return nums[0] if nums else None

    num = prefer(numeric)
    qs = [f"How many rows are in the {table} table?"]
    if num:
        qs.append(f"What is the average {_pretty(num)}?")
    if categorical:
        qs.append(f"How many rows are there for each {_pretty(categorical[0])}?")
    if categorical and num:
        qs.append(f"What is the total {_pretty(num)} by {_pretty(categorical[0])}?")
    if len(categorical) > 1:
        qs.append(f"What are the top 5 {_pretty(categorical[1])} by count?")
    elif len(numeric) > 1:
        other = numeric[1] if numeric[1] != num else numeric[0]
        qs.append(f"What is the highest {_pretty(other)}?")
    if dated and num:
        qs.append(f"What is the average {_pretty(num)} by month?")
    return qs[:5]
