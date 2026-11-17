# -*- coding: utf-8 -*-
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import seekindex as mod  # noqa: E402
seekindex = mod

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "chunks.json")


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
    chunks = seekindex.load_chunks(DATA)
    idx = seekindex.build_index(chunks)
    assert idx, "索引不应为空"
    hit = seekindex.seek_time(idx, 1830)
    assert hit["offset"] >= 0


def test_seek_never_overshoots():
    chunks = seekindex.load_chunks(DATA)
    idx = seekindex.build_index(chunks)
    for t in (0, 900, 1830, 5000):
        hit = seekindex.seek_time(idx, t)
        assert hit["start_ms"] <= t


def test_index_disk_roundtrip_identical(tmp_path):
    chunks = seekindex.load_chunks(DATA)
    idx = seekindex.build_index(chunks)
    p = tmp_path / "index.json"
    seekindex.save_index(idx, str(p))
    idx2 = seekindex.load_index(str(p))
    assert idx.keys == idx2.keys
    for t in (0, 450, 900, 1830, 2699, 5000, -1):
        assert seekindex.seek_time(idx, t) == seekindex.seek_time(idx2, t)


def test_fallback_delta_and_limit():
    chunks = seekindex.load_chunks(DATA)
    idx = seekindex.build_index(chunks)
    hit = seekindex.seek_time(idx, 1830)
    assert hit["ok"] is True
    assert hit["start_ms"] == 1800
    assert hit["offset"] == 1800
    assert hit["delta_ms"] == 30
    # 偏差超过上限要报错，而不是悄悄给更早的位置
    with pytest.raises(seekindex.SeekError):
        seekindex.seek_time(idx, 1799, max_delta_ms=500)


def test_boundary_results():
    chunks = seekindex.load_chunks(DATA)
    idx = seekindex.build_index(chunks)
    before = seekindex.seek_time(idx, -1)
    assert before["ok"] is False
    assert before["boundary"] == "before_first"
    after = seekindex.seek_time(idx, 2701)
    assert after["ok"] is False
    assert after["boundary"] == "after_last"
    # 末点本身仍可命中
    edge = seekindex.seek_time(idx, 2700)
    assert edge["ok"] is True


def test_duplicate_timestamps_first_wins():
    chunks = [
        seekindex.Chunk(start_ms=100, end_ms=200, offset=1000, size=10),
        seekindex.Chunk(start_ms=100, end_ms=250, offset=2000, size=20),
        seekindex.Chunk(start_ms=50, end_ms=100, offset=500, size=10),
    ]
    idx = seekindex.build_index(chunks)
    assert idx.keys == [50, 100]
    hit = seekindex.seek_time(idx, 100)
    assert hit["offset"] == 1000  # 先出现的条目胜出
    assert seekindex.nearest_key(idx, 100) == 100
    assert seekindex.nearest_key(idx, 99) == 50
    assert seekindex.nearest_key(idx, 49) is None


def test_deterministic_across_runs(tmp_path):
    chunks = seekindex.load_chunks(DATA)
    results = []
    for _ in range(2):
        idx = seekindex.build_index(chunks)
        results.append([seekindex.seek_time(idx, t) for t in (0, 1830, 5000)])
    assert results[0] == results[1]
    p1, p2 = tmp_path / "a.json", tmp_path / "b.json"
    seekindex.save_index(seekindex.build_index(chunks), str(p1))
    seekindex.save_index(seekindex.build_index(chunks), str(p2))
    assert read_bytes(str(p1)) == read_bytes(str(p2))
