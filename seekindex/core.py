# -*- coding: utf-8 -*-
"""字节索引与精确 seek。

按时间戳建立索引，定位到承载该时刻的块及其字节偏移；
只回退、不越过请求时刻；回退偏差超限时报错。
另提供多级（稀疏锚点）索引、批量定位与落盘/读回。
仅使用 Python 标准库。
"""

import bisect
import json
from dataclasses import dataclass


class SeekError(Exception):
    """回退偏差超过上限，或索引为空等无法定位的情况。"""


@dataclass
class Chunk:
    """一个可 seek 的数据块。"""
    start_ms: int
    end_ms: int
    offset: int
    size: int


# ---------------------------------------------------------------------------
# 单层索引
# ---------------------------------------------------------------------------

class Index:
    """单层时间->字节索引。

    entries: 按 start_ms 升序的 (start_ms, Chunk) 列表；
    重复时间戳只保留第一次出现的块。
    """

    def __init__(self, entries, max_backoff_ms=None):
        self.entries = list(entries)
        self.max_backoff_ms = max_backoff_ms
        self._keys = [e[0] for e in self.entries]

    def __len__(self):
        return len(self.entries)

    def __bool__(self):
        return bool(self.entries)

    def to_dict(self):
        return {
            "max_backoff_ms": self.max_backoff_ms,
            "entries": [
                {
                    "start_ms": c.start_ms,
                    "end_ms": c.end_ms,
                    "offset": c.offset,
                    "size": c.size,
                }
                for _, c in self.entries
            ],
        }

    @classmethod
    def from_dict(cls, data):
        entries = [
            (
                int(e["start_ms"]),
                Chunk(
                    start_ms=int(e["start_ms"]),
                    end_ms=int(e["end_ms"]),
                    offset=int(e["offset"]),
                    size=int(e["size"]),
                ),
            )
            for e in data["entries"]
        ]
        return cls(entries, max_backoff_ms=data.get("max_backoff_ms"))


def _coerce_chunk(c):
    """把 dict 或 Chunk 统一成 Chunk；缺 offset/size 时退化为 0。"""
    if isinstance(c, Chunk):
        return c
    return Chunk(
        start_ms=int(c["start_ms"]),
        end_ms=int(c["end_ms"]),
        offset=int(c.get("offset", 0)),
        size=int(c.get("size", 0)),
    )


def build_index(chunks, max_backoff_ms=None):
    """建时间到字节的索引。

    重复 start_ms 按出现顺序取第一个；条目按 start_ms 升序排列。
    max_backoff_ms 为回退偏差上限（毫秒），seek 时超限抛 SeekError。
    """
    seen = set()
    entries = []
    for raw in chunks:
        c = _coerce_chunk(raw)
        if c.start_ms in seen:
            continue
        seen.add(c.start_ms)
        entries.append((c.start_ms, c))
    entries.sort(key=lambda e: e[0])
    return Index(entries, max_backoff_ms=max_backoff_ms)


def nearest_key(index, t_ms):
    """找不晚于该时刻的键；早于首点时返回 None。"""
    if not index.entries:
        return None
    i = bisect.bisect_right(index._keys, t_ms) - 1
    if i < 0:
        return None
    return index._keys[i]


def _limit_of(index, max_backoff_ms):
    return index.max_backoff_ms if max_backoff_ms is None else max_backoff_ms


def seek_time(index, t_ms, max_backoff_ms=None):
    """返回落点与偏差。

    命中规则：只回退到不晚于 t_ms 的关键点。
    返回 dict(start_ms, end_ms, offset, size, backoff_ms, boundary)。
    boundary 为 None / "before_first" / "after_last"。
    回退偏差超过上限（参数或索引自带）时抛 SeekError。
    """
    if not index.entries:
        raise SeekError("空索引，无法定位")
    limit = _limit_of(index, max_backoff_ms)
    keys = index._keys

    if t_ms < keys[0]:
        c = index.entries[0][1]
        return {
            "start_ms": c.start_ms,
            "end_ms": c.end_ms,
            "offset": c.offset,
            "size": c.size,
            "backoff_ms": 0,
            "boundary": "before_first",
        }

    i = bisect.bisect_right(keys, t_ms) - 1
    boundary = None
    if i == len(keys) - 1 and t_ms >= index.entries[-1][1].end_ms:
        boundary = "after_last"
    c = index.entries[i][1]
    backoff = t_ms - c.start_ms
    if limit is not None and backoff > limit:
        raise SeekError(
            "回退偏差 %d ms 超过上限 %d ms（请求时刻 %d）"
            % (backoff, limit, t_ms)
        )
    return {
        "start_ms": c.start_ms,
        "end_ms": c.end_ms,
        "offset": c.offset,
        "size": c.size,
        "backoff_ms": backoff,
        "boundary": boundary,
    }


# ---------------------------------------------------------------------------
# 落盘 / 读回
# ---------------------------------------------------------------------------

def load_chunks(path):
    """从 JSON 文件读入块列表，返回 list[Chunk]。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [_coerce_chunk(d) for d in data]


def save_index(index, path):
    """索引落盘（JSON，键排序，保证字节级确定）。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index.to_dict(), f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def load_index(path):
    """读回落盘的索引；读回后 seek 结果与内存索引完全一致。"""
    with open(path, "r", encoding="utf-8") as f:
        return Index.from_dict(json.load(f))


# ---------------------------------------------------------------------------
# 多级索引
# ---------------------------------------------------------------------------

def _block_id(raw, c, i):
    """块的对外标识：dict 优先 path/id/offset，Chunk 用 offset，否则用序号。"""
    if isinstance(raw, dict):
        for k in ("path", "id", "offset"):
            if k in raw:
                return raw[k]
        return i
    return c.offset


class TieredIndex:
    """多级索引：level 0 放全部块起点，更高层每 fanout 个取一个稀疏锚点。"""

    def __init__(self, blocks, fanout):
        # blocks: list of (start_ms, end_ms, block_id)，已按 start_ms 升序去重
        self.blocks = blocks
        self.fanout = fanout
        # levels[0] 为底层（全部块起点），levels[-1] 为最稀疏的顶层
        self.levels = []
        level = list(range(len(blocks)))  # 存块下标
        self.levels.append(level)
        while len(level) > 1:
            level = level[::fanout]
            self.levels.append(level)

    # -- 内部 ------------------------------------------------------------
    def _key(self, lvl, pos):
        return self.blocks[self.levels[lvl][pos]][0]

    def _descend(self, t_ms):
        """从顶层逐级下降，返回 (块下标, 跨级数)。"""
        n_levels = len(self.levels)
        # 顶层：找不晚于 t 的锚点
        top = self.levels[-1]
        keys = [self.blocks[b][0] for b in top]
        i = bisect.bisect_right(keys, t_ms) - 1
        if i < 0:
            i = 0
        lo_block = top[i]
        # 下一层的搜索范围：[i*fanout, (i+1)*fanout)
        lo = i * self.fanout
        hi = lo + self.fanout
        for lvl in range(n_levels - 2, -1, -1):
            level = self.levels[lvl]
            lo = min(lo, len(level) - 1)
            hi = min(hi, len(level))
            keys = [self.blocks[b][0] for b in level[lo:hi]]
            j = bisect.bisect_right(keys, t_ms) - 1
            if j < 0:
                j = 0
            block_idx = level[lo + j]
            # 计算更下一层的范围
            lo = (lo + j) * self.fanout
            hi = lo + self.fanout
            lo_block = block_idx
        return lo_block, n_levels

    # -- 对外 ------------------------------------------------------------
    def seek(self, t_ms):
        if not self.blocks:
            raise SeekError("空索引，无法定位")
        starts = [b[0] for b in self.blocks]
        if t_ms < starts[0]:
            start, end, bid = self.blocks[0]
            return {
                "block": bid,
                "start_ms": start,
                "end_ms": end,
                "backoff_ms": 0,
                "levels": len(self.levels),
                "boundary": "before_first",
            }
        idx, n_levels = self._descend(t_ms)
        start, end, bid = self.blocks[idx]
        boundary = None
        if idx == len(self.blocks) - 1 and t_ms >= end:
            boundary = "after_last"
        return {
            "block": bid,
            "start_ms": start,
            "end_ms": end,
            "backoff_ms": t_ms - start,
            "levels": n_levels,
            "boundary": boundary,
        }

    def stats(self):
        return {
            "entries": sum(len(l) for l in self.levels),
            "levels": len(self.levels),
            "chunks": len(self.blocks),
        }


def build_tiered_index(chunks, fanout=8):
    """多级索引：返回索引对象，含 levels 与 entries。

    底层放全部块起点；更高层每 fanout 个条目取一个稀疏锚点。
    重复 start_ms 按出现顺序取第一个。
    """
    if fanout < 2:
        raise ValueError("fanout 必须 >= 2")
    seen = set()
    blocks = []
    for i, raw in enumerate(chunks):
        c = _coerce_chunk(raw)
        if c.start_ms in seen:
            continue
        seen.add(c.start_ms)
        blocks.append((c.start_ms, c.end_ms, _block_id(raw, c, i)))
    blocks.sort(key=lambda b: b[0])
    return TieredIndex(blocks, fanout)


def seek_in(index, t_ms):
    """定位落点：返回 dict(block=块标识, backoff_ms=回退毫秒, levels=跨级数)。"""
    return index.seek(t_ms)


def seek_many(index, times):
    """批量定位：返回 list(dict)，与逐个 seek_in 完全一致。"""
    return [index.seek(t) for t in times]


def index_stats(index):
    """返回 dict(entries=条目数, levels=级数, chunks=块数)。"""
    return index.stats()
