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


def Chunk:
    """class"""
    raise NotImplementedError("Chunk 尚未实现")


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

