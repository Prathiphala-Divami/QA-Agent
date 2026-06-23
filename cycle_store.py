from __future__ import annotations
import json
import os

STORE_FILE = os.path.join(os.path.dirname(__file__), "cycles.json")


def _load() -> dict:
    if not os.path.exists(STORE_FILE):
        return {}
    with open(STORE_FILE) as f:
        return json.load(f)


def _save(data: dict) -> None:
    with open(STORE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_cycle(name: str) -> dict | None:
    return _load().get(name)


def set_cycle(name: str, data: dict) -> None:
    store = _load()
    store[name] = data
    _save(store)


def list_cycles() -> list[str]:
    return list(_load().keys())
