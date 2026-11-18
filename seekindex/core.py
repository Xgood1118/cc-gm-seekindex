# -*- coding: utf-8 -*-
"""字节索引与精确 seek"""

from dataclasses import dataclass


@dataclass
class Chunk:
    """一个可 seek 的数据块。"""
    start_ms: int
    end_ms: int
    offset: int
    size: int




def build_index(chunks):
    """建时间到字节的索引"""
    raise NotImplementedError("build_index 尚未实现")


def seek_time(index, t_ms):
    """返回落点与偏差"""
    raise NotImplementedError("seek_time 尚未实现")


def nearest_key(index, t_ms):
    """找不晚于该时刻的键"""
    raise NotImplementedError("nearest_key 尚未实现")


def load_chunks(path):
    """读入与落盘辅助"""
    raise NotImplementedError("load_chunks 尚未实现")



def build_tiered_index(chunks, fanout=8):
    """多级索引：返回索引对象，含 levels 与 entries。"""
    raise NotImplementedError("build_tiered_index 尚未实现")


def seek_in(index, t_ms):
    """定位落点：返回 dict(block=块标识, backoff_ms=回退毫秒, levels=跨级数)。"""
    raise NotImplementedError("seek_in 尚未实现")


def seek_many(index, times):
    """批量定位：返回 list(dict)，与逐个 seek_in 完全一致。"""
    raise NotImplementedError("seek_many 尚未实现")


def index_stats(index):
    """返回 dict(entries=条目数, levels=级数, chunks=块数)。"""
    raise NotImplementedError("index_stats 尚未实现")
