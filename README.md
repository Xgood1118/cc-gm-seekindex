# 字节索引与精确 seek

一个能按字节索引定位、并给出精确落点误差的 seek 定位器。仅用 Python 标准库。

## 保留签名

- `Chunk`
- `build_index(chunks)`
- `seek_time(index, t_ms)`
- `nearest_key(index, t_ms)`

另提供 `load_chunks` / `save_index` / `load_index` 用于读入数据与索引落盘往返。

## 索引

- `build_index(chunks)` 按 `start_ms` 升序建索引（稳定排序），每个关键点记录
  承载该时刻的样本在字节流中的 `offset` / `size`。
- **重复时间戳规则**：`start_ms` 重复时按出现顺序取第一个，后续重复条目丢弃。
- `save_index` / `load_index` 把索引落成 JSON 再读回；序列化键序固定，
  同一份索引两次落盘字节完全一致，读回后 seek 结果与内存索引完全一致。

## 定位

- `seek_time(index, t_ms, max_delta_ms=1000)` 只回退到不晚于请求时刻的最近关键点，
  返回 `delta_ms`（回退偏差，毫秒）。
- `delta_ms` 超过 `max_delta_ms` 时抛 `seekindex.SeekError`，不会悄悄给更早的位置。
- `nearest_key(index, t_ms)` 返回不晚于 `t_ms` 的键，没有则返回 `None`。

## 边界

- `t_ms` 早于首点：返回 `{"ok": False, "boundary": "before_first", ...}`。
- `t_ms` 晚于末点（最后一条目的 `end_ms`）：返回 `{"ok": False, "boundary": "after_last", ...}`。
- 命中时返回 `{"ok": True, "start_ms", "end_ms", "offset", "size", "delta_ms", "t_ms"}`。

## 自测

```
python -m pytest tests -q
python -m seekindex.cli data/chunks.json --at 1830 --out hit.json
```

## 实测（data/chunks.json，--at 1830）

- 请求时刻：1830 ms
- 落点偏移：1800（start_ms=1800，size=900）
- 回退偏差：30 ms
- 索引条目数：3
