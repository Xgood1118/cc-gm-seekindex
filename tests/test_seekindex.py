# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import seekindex as mod  # noqa: E402


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


# ===== v2 契约测试：初始全部失败，实现后必须通过 =====
import seekindex  # noqa: E402


def _chunks():
    return [{"start_ms": t, "end_ms": t + 400, "path": "c%d" % i}
            for i, t in enumerate([0, 500, 1000, 1500, 2000, 4000, 4500])]


def test_tiered_index_matches_flat_order():
    ch = _chunks()
    idx = seekindex.build_tiered_index(ch, fanout=4)
    r = seekindex.seek_in(idx, 120)
    assert r["block"] == ch[0]["path"]
    r2 = seekindex.seek_in(idx, 1400)
    assert r2["block"] in (ch[2]["path"], ch[3]["path"])


def test_sparse_gap_reports_backoff():
    idx = seekindex.build_tiered_index(_chunks(), fanout=4)
    r = seekindex.seek_in(idx, 2600)
    assert r["backoff_ms"] >= 400
    assert r["block"] in ("c3", "c4")


def test_seek_many_matches_single():
    idx = seekindex.build_tiered_index(_chunks(), fanout=4)
    ts = [0, 999, 2500, 4600]
    many = seekindex.seek_many(idx, ts)
    for t, r in zip(ts, many):
        assert r["block"] == seekindex.seek_in(idx, t)["block"]


def test_entries_shrink_with_fanout():
    ch = [{"start_ms": i * 100, "end_ms": i * 100 + 50, "path": "c%d" % i} for i in range(64)]
    small = seekindex.index_stats(seekindex.build_tiered_index(ch, fanout=64))
    big = seekindex.index_stats(seekindex.build_tiered_index(ch, fanout=4))
    assert big["entries"] <= small["entries"] * 40
    assert big["levels"] >= 1
