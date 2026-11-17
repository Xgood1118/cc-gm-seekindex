# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import seekindex as mod  # noqa: E402
seekindex = mod

def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_hex(path):
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def test_index_roundtrip(tmp_path):
    chunks = seekindex.load_chunks("data/chunks.json")
    idx = seekindex.build_index(chunks)
    assert idx, "索引不应为空"
    hit = seekindex.seek_time(idx, 1830)
    assert hit["offset"] >= 0


def test_seek_never_overshoots():
    chunks = seekindex.load_chunks("data/chunks.json")
    idx = seekindex.build_index(chunks)
    for t in (0, 900, 1830, 5000):
        hit = seekindex.seek_time(idx, t)
        assert hit["start_ms"] <= t
