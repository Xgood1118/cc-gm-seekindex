# -*- coding: utf-8 -*-
"""本轮新增要求的契约测试：索引落盘、回退上限、边界、去重、
确定性、多级索引一致性、批量一致性、条目规模。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import seekindex  # noqa: E402


DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "chunks.json")


def _dict_chunks():
    return [{"start_ms": t, "end_ms": t + 400, "path": "c%d" % i}
            for i, t in enumerate([0, 500, 1000, 1500, 2000, 4000, 4500])]


# ---- 1. 索引：定位到样本与字节偏移；落盘读回一致 --------------------------

def test_index_locates_byte_offset():
    idx = seekindex.build_index(seekindex.load_chunks(DATA))
    hit = seekindex.seek_time(idx, 1830)
    assert hit["start_ms"] == 1800
    assert hit["offset"] == 1800
    assert hit["size"] == 900
    assert hit["backoff_ms"] == 30


def test_index_disk_roundtrip_identical(tmp_path):
    idx = seekindex.build_index(seekindex.load_chunks(DATA))
    p = str(tmp_path / "index.json")
    seekindex.save_index(idx, p)
    idx2 = seekindex.load_index(p)
    for t in (0, 1, 899, 900, 1830, 2699, 2700, 99999):
        assert seekindex.seek_time(idx, t) == seekindex.seek_time(idx2, t)


# ---- 2. 定位：只回退并给出偏差；超限报错 ----------------------------------

def test_fallback_reports_backoff():
    idx = seekindex.build_index(seekindex.load_chunks(DATA))
    hit = seekindex.seek_time(idx, 1000)
    assert hit["start_ms"] == 900
    assert hit["backoff_ms"] == 100
    assert hit["start_ms"] <= 1000


def test_backoff_over_limit_raises():
    chunks = [{"start_ms": 0, "end_ms": 100, "offset": 0, "size": 100},
              {"start_ms": 5000, "end_ms": 5100, "offset": 100, "size": 100}]
    idx = seekindex.build_index(chunks, max_backoff_ms=500)
    with pytest.raises(seekindex.SeekError):
        seekindex.seek_time(idx, 2000)  # 回退 2000ms > 500ms 上限
    # 不超限时正常返回
    assert seekindex.seek_time(idx, 400)["start_ms"] == 0
    # seek_time 的参数可覆盖索引自带上限
    assert seekindex.seek_time(idx, 2000, max_backoff_ms=3000)["start_ms"] == 0


def test_nearest_key():
    idx = seekindex.build_index(seekindex.load_chunks(DATA))
    assert seekindex.nearest_key(idx, 1830) == 1800
    assert seekindex.nearest_key(idx, 0) == 0
    assert seekindex.nearest_key(idx, -1) is None


# ---- 3. 边界：早于首点 / 晚于末点；重复时间戳取第一个 ----------------------

def test_boundary_before_first_and_after_last():
    idx = seekindex.build_index(seekindex.load_chunks(DATA))
    early = seekindex.seek_time(idx, -100)
    assert early["boundary"] == "before_first"
    assert early["start_ms"] == 0
    late = seekindex.seek_time(idx, 99999)
    assert late["boundary"] == "after_last"
    assert late["start_ms"] == 2700 - 900
    inside = seekindex.seek_time(idx, 1830)
    assert inside["boundary"] is None


def test_duplicate_timestamps_keep_first():
    chunks = [
        {"start_ms": 100, "end_ms": 200, "offset": 7, "size": 10},
        {"start_ms": 100, "end_ms": 200, "offset": 99, "size": 10},
        {"start_ms": 100, "end_ms": 200, "offset": 55, "size": 10},
    ]
    idx = seekindex.build_index(chunks)
    assert len(idx) == 1
    assert seekindex.seek_time(idx, 150)["offset"] == 7


# ---- 4. 输出确定性 ---------------------------------------------------------

def test_same_index_same_result_twice():
    idx = seekindex.build_index(seekindex.load_chunks(DATA))
    for t in (0, 450, 1830, 5000):
        assert seekindex.seek_time(idx, t) == seekindex.seek_time(idx, t)


# ---- 5. 多级索引：与单层命中相同块、报告级数；稀疏空档回退 ------------------

def test_tiered_matches_flat_for_all_times():
    chunks = seekindex.load_chunks(DATA)
    flat = seekindex.build_index(chunks)
    tiered = seekindex.build_tiered_index(chunks, fanout=2)
    for t in range(0, 3000, 7):
        f = seekindex.seek_time(flat, t)
        r = seekindex.seek_in(tiered, t)
        assert r["block"] == f["offset"]
        assert r["backoff_ms"] == f["backoff_ms"]
        assert r["levels"] >= 1


def test_tiered_sparse_gap_backoff_ms():
    idx = seekindex.build_tiered_index(_dict_chunks(), fanout=4)
    r = seekindex.seek_in(idx, 2600)  # 落在 2400~4000 的空档
    assert r["block"] == "c4"
    assert r["backoff_ms"] == 600  # 2600 - 2000，精确到毫秒


def test_tiered_boundaries():
    idx = seekindex.build_tiered_index(_dict_chunks(), fanout=4)
    assert seekindex.seek_in(idx, -5)["boundary"] == "before_first"
    assert seekindex.seek_in(idx, 10 ** 9)["boundary"] == "after_last"


# ---- 6. 批量一致与条目规模 -------------------------------------------------

def test_seek_many_equals_single():
    idx = seekindex.build_tiered_index(_dict_chunks(), fanout=4)
    ts = [0, 120, 999, 2500, 2600, 4600, 10 ** 9]
    assert seekindex.seek_many(idx, ts) == [seekindex.seek_in(idx, t) for t in ts]


def test_entries_decrease_with_fanout_and_stay_linear():
    ch = [{"start_ms": i * 100, "end_ms": i * 100 + 50, "path": "c%d" % i}
          for i in range(64)]
    stats = {f: seekindex.index_stats(seekindex.build_tiered_index(ch, fanout=f))
             for f in (2, 4, 8, 64)}
    for s in stats.values():
        assert s["chunks"] == 64
        assert s["levels"] >= 1
        # 条目数不超过块数的量级（等比级数 <= n * fanout/(fanout-1)）
        assert s["entries"] <= 2 * s["chunks"]
    e = [stats[f]["entries"] for f in (2, 4, 8, 64)]
    assert e == sorted(e, reverse=True), "条目数必须随扇出增大而下降"
    assert stats[2]["levels"] >= stats[64]["levels"]


# ---- 退化场景 ---------------------------------------------------------------

def test_empty_index_raises():
    idx = seekindex.build_index([])
    with pytest.raises(seekindex.SeekError):
        seekindex.seek_time(idx, 0)
    assert seekindex.nearest_key(idx, 0) is None


def test_single_chunk():
    idx = seekindex.build_index(
        [{"start_ms": 10, "end_ms": 20, "offset": 3, "size": 5}])
    assert seekindex.seek_time(idx, 10)["offset"] == 3
    assert seekindex.seek_time(idx, 15)["backoff_ms"] == 5
    assert seekindex.seek_time(idx, 9)["boundary"] == "before_first"
    t = seekindex.build_tiered_index(
        [{"start_ms": 10, "end_ms": 20, "path": "only"}], fanout=4)
    assert seekindex.seek_in(t, 15)["block"] == "only"
    assert seekindex.index_stats(t)["levels"] == 1


def test_exact_key_hits_zero_backoff():
    idx = seekindex.build_index(seekindex.load_chunks(DATA))
    hit = seekindex.seek_time(idx, 900)
    assert hit["start_ms"] == 900
    assert hit["backoff_ms"] == 0


def test_tiered_duplicate_timestamps_keep_first():
    ch = [{"start_ms": 100, "end_ms": 200, "path": "first"},
          {"start_ms": 100, "end_ms": 200, "path": "second"}]
    idx = seekindex.build_tiered_index(ch, fanout=2)
    assert seekindex.seek_in(idx, 150)["block"] == "first"


def test_invalid_fanout_rejected():
    with pytest.raises(ValueError):
        seekindex.build_tiered_index(_dict_chunks(), fanout=1)
