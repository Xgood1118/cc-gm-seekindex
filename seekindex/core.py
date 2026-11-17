# -*- coding: utf-8 -*-
"""字节索引与精确 seek"""

import bisect
import json
from dataclasses import dataclass

#: seek 回退偏差的默认上限（毫秒）
DEFAULT_MAX_DELTA_MS = 1000

INDEX_FORMAT_VERSION = 1


class SeekError(Exception):
    """seek 失败（如回退偏差超过上限）。"""


@dataclass
class Chunk:
    """一个可 seek 的数据块。"""
    start_ms: int
    end_ms: int
    offset: int
    size: int


class Index:
    """时间戳 -> 字节偏移 的有序索引。

    entries 按 start_ms 升序；start_ms 重复时保留输入中先出现的条目。
    """

    def __init__(self, entries):
        # entries: list[Chunk]，已按 start_ms 升序、去重
        self._entries = list(entries)
        self._keys = [c.start_ms for c in self._entries]

    def __len__(self):
        return len(self._entries)

    def __bool__(self):
        return bool(self._entries)

    @property
    def entries(self):
        return list(self._entries)

    @property
    def keys(self):
        return list(self._keys)

    @property
    def first_start_ms(self):
        return self._keys[0] if self._keys else None

    @property
    def last_end_ms(self):
        return self._entries[-1].end_ms if self._entries else None

    def to_dict(self):
        return {
            "version": INDEX_FORMAT_VERSION,
            "entries": [
                {
                    "start_ms": c.start_ms,
                    "end_ms": c.end_ms,
                    "offset": c.offset,
                    "size": c.size,
                }
                for c in self._entries
            ],
        }

    @classmethod
    def from_dict(cls, data):
        if data.get("version") != INDEX_FORMAT_VERSION:
            raise SeekError("不支持的索引版本: %r" % (data.get("version"),))
        entries = [
            Chunk(
                start_ms=int(e["start_ms"]),
                end_ms=int(e["end_ms"]),
                offset=int(e["offset"]),
                size=int(e["size"]),
            )
            for e in data["entries"]
        ]
        return cls(entries)


def build_index(chunks):
    """建时间到字节的索引。

    按 start_ms 升序排序（稳定排序）；start_ms 重复时按出现顺序取第一个。
    """
    ordered = sorted(chunks, key=lambda c: c.start_ms)
    entries = []
    seen = set()
    for c in ordered:
        if c.start_ms in seen:
            continue
        seen.add(c.start_ms)
        entries.append(c)
    return Index(entries)


def nearest_key(index, t_ms):
    """找不晚于该时刻的键；没有则返回 None。"""
    if not index:
        return None
    i = bisect.bisect_right(index.keys, t_ms) - 1
    if i < 0:
        return None
    return index.keys[i]


def seek_time(index, t_ms, max_delta_ms=DEFAULT_MAX_DELTA_MS):
    """返回落点与偏差。

    命中时返回 dict(ok=True, ...)，落点是不晚于 t_ms 的最近关键点，
    delta_ms 为回退偏差；delta_ms 超过 max_delta_ms 时抛 SeekError。
    t_ms 早于首点或晚于末点时返回 dict(ok=False, boundary=...)。
    """
    if not index:
        raise SeekError("空索引")
    t_ms = int(t_ms)
    first = index.first_start_ms
    last_end = index.last_end_ms
    if t_ms < first:
        return {
            "ok": False,
            "boundary": "before_first",
            "t_ms": t_ms,
            "start_ms": first,
            "first_start_ms": first,
            "last_end_ms": last_end,
        }
    if t_ms > last_end:
        last = index.entries[-1]
        return {
            "ok": False,
            "boundary": "after_last",
            "t_ms": t_ms,
            "start_ms": last.start_ms,
            "first_start_ms": first,
            "last_end_ms": last_end,
        }
    key = nearest_key(index, t_ms)
    i = bisect.bisect_left(index.keys, key)
    chunk = index.entries[i]
    delta = t_ms - chunk.start_ms
    if max_delta_ms is not None and delta > max_delta_ms:
        raise SeekError(
            "回退偏差 %d ms 超过上限 %d ms（请求 %d，落点 %d）"
            % (delta, max_delta_ms, t_ms, chunk.start_ms)
        )
    return {
        "ok": True,
        "t_ms": t_ms,
        "start_ms": chunk.start_ms,
        "end_ms": chunk.end_ms,
        "offset": chunk.offset,
        "size": chunk.size,
        "delta_ms": delta,
    }


def load_chunks(path):
    """读入 chunk 列表（JSON）。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [
        Chunk(
            start_ms=int(e["start_ms"]),
            end_ms=int(e["end_ms"]),
            offset=int(e["offset"]),
            size=int(e["size"]),
        )
        for e in data
    ]


def save_index(index, path):
    """索引落盘（JSON，键序固定，保证字节级可复现）。"""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(index.to_dict(), f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")


def load_index(path):
    """读回落盘的索引；读回后 seek 结果与内存索引一致。"""
    with open(path, encoding="utf-8") as f:
        return Index.from_dict(json.load(f))
