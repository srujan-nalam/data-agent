"""Phase 5 memory.

Two pieces, both deliberately simple (no vector DB — for structured data,
schema + keyword retrieval carries most of the weight):

  SchemaCache  — remember a dataset's schema so schema_inspector introspects
                 the warehouse once, not on every question.
  QueryLibrary — remember successful (question -> SQL) pairs per dataset, and
                 retrieve similar past queries as few-shot hints for the
                 drafter. Persisted to JSON so it survives restarts.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter


class SchemaCache:
    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}

    def get(self, dataset_id: str):
        return self._cache.get(dataset_id)

    def set(self, dataset_id: str, schema: dict) -> None:
        self._cache[dataset_id] = schema


def _tokens(text: str) -> Counter:
    return Counter(re.findall(r"[a-z0-9]+", text.lower()))


class QueryLibrary:
    def __init__(self, path: str = "data/query_library.json") -> None:
        self.path = path
        self._items: list[dict] = []
        if os.path.exists(path):
            try:
                self._items = json.load(open(path))
            except Exception:
                self._items = []

    def add(self, dataset_id: str, question: str, sql: str) -> None:
        # de-dupe on (dataset, question)
        self._items = [
            it for it in self._items
            if not (it["dataset_id"] == dataset_id and it["question"] == question)
        ]
        self._items.append({"dataset_id": dataset_id, "question": question, "sql": sql})
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            json.dump(self._items, open(self.path, "w"), indent=2)
        except Exception:
            pass

    def retrieve(self, dataset_id: str, question: str, k: int = 2) -> list[dict]:
        q = _tokens(question)
        scored = []
        for it in self._items:
            if it["dataset_id"] != dataset_id:
                continue
            overlap = sum((q & _tokens(it["question"])).values())
            if overlap:
                scored.append((overlap, it))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [it for _, it in scored[:k]]


class Memory:
    """Bundle passed to the graph."""
    def __init__(self, library_path: str = "data/query_library.json") -> None:
        self.schema = SchemaCache()
        self.library = QueryLibrary(library_path)
