#!/usr/bin/env python3
"""Self-check for collect.py's local transcript readers.

Run: python scripts/test_collect.py   (or: uv run scripts/test_collect.py)

Synthetic fixtures only — no machine data, no network, standard library only.
"""

import datetime as dt
import json
import os
import shutil
import tempfile

import collect

TZ = "Asia/Shanghai"
BIG = (dt.date(2020, 1, 1), dt.date(2100, 1, 1))
TS = 1756300000000  # any epoch-ms inside BIG


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(obj if isinstance(obj, str) else json.dumps(obj) + "\n")


def test_cline():
    root = tempfile.mkdtemp()
    os.environ["CLINE_DIR"] = root
    try:
        write(os.path.join(root, "data", "sessions", "s1", "s1.messages.json"), {"messages": [
            {"ts": TS, "metrics": {"inputTokens": 100, "outputTokens": 10,
                                   "cacheReadTokens": 5, "cacheWriteTokens": 2},
             "modelInfo": {"id": "m1"}},
            {"ts": TS, "modelInfo": {"id": "m1"}},  # no metrics -> ignored
        ]})
        days = collect.fetch_cline(*BIG, tz_name=TZ)
        assert len(days) == 1, days
        rec = list(days.values())[0]
        assert (rec["input"], rec["output"]) == (100, 10), rec
        assert (rec["cacheRead"], rec["cacheCreation"]) == (5, 2), rec
        assert rec["total"] == 117 and rec["models"]["m1"]["total"] == 117, rec
        assert collect.fetch_cline(dt.date(2020, 1, 1), dt.date(2020, 1, 2), TZ) == {}
    finally:
        os.environ.pop("CLINE_DIR", None)
        shutil.rmtree(root, ignore_errors=True)


def test_workbuddy():
    root = tempfile.mkdtemp()
    os.environ["WORKBUDDY_DIR"] = root
    try:
        full = {"id": "u1", "timestamp": TS, "type": "function_call",
                "providerData": {"model": "glm-5.2", "rawUsage": {
                    "prompt_tokens": 1000, "prompt_cache_hit_tokens": 800,
                    "prompt_cache_miss_tokens": 200, "completion_tokens": 50,
                    "cache_creation_input_tokens": 7,
                    "credit": 1.23456789,
                    "completion_tokens_details": {"reasoning_tokens": 20}}}}
        sparse = {"id": "u2", "timestamp": TS, "type": "function_call",
                  "providerData": {"model": "hy3", "rawUsage": {
                      "prompt_tokens": 500, "cache_read_input_tokens": 100,
                      "completion_tokens": 5}}}
        write(os.path.join(root, "projects", "p", "s.jsonl"),
              json.dumps(full) + "\n" + json.dumps(sparse) + "\n")
        write(os.path.join(root, "projects", "p", "s", "subagents", "a.jsonl"), full)  # same id, deduped
        days = collect.fetch_workbuddy(*BIG, tz_name=TZ)
        assert len(days) == 1, days
        rec = list(days.values())[0]
        assert (rec["input"], rec["output"]) == (600, 55), rec          # miss side + fallback miss
        assert (rec["cacheRead"], rec["cacheCreation"]) == (900, 7), rec  # hit side
        assert rec["total"] == 1562, rec
        assert rec["models"]["glm-5.2"]["total"] == 1057, rec           # deduped, additive
        assert "credits" not in rec and "reasoningOutput" not in rec, rec  # token-only schema
    finally:
        os.environ.pop("WORKBUDDY_DIR", None)
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    test_cline()
    test_workbuddy()
    print("OK")
