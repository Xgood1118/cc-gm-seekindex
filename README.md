# 字节索引与精确 seek

一个能按字节索引定位、并给出精确落点误差的 seek 定位器。仅用 Python 标准库。

## 保留签名

- `Chunk`
- `build_index(chunks)`
- `seek_time(index, t_ms)`
- `nearest_key(index, t_ms)`

## 规则

- **只回退不越过**：请求时刻落在两个关键点之间时，定位到不晚于该时刻的最近关键点，
  并在结果的 `backoff_ms` 字段给出精确回退偏差（毫秒）。
- **回退上限**：`build_index(chunks, max_backoff_ms=...)` 或 `seek_time(..., max_backoff_ms=...)`
  可设上限；回退偏差超限抛 `SeekError`，绝不悄悄给更早的位置。
- **边界**：请求时刻早于首点返回首点并标 `boundary="before_first"`；
  晚于末块结束返回末点并标 `boundary="after_last"`；正常命中为 `None`。
- **重复时间戳**：同一 `start_ms` 出现多次时，**按出现顺序取第一个**，其余丢弃。
- **确定性**：同一份索引连跑两次结果完全一致；索引可 `save_index`/`load_index`
  落盘读回，读回后 seek 结果与内存索引逐字段一致。

## 多级索引

`build_tiered_index(chunks, fanout=8)`：底层（level 0）放全部块起点，
更高层每 `fanout` 个条目取一个稀疏锚点。`seek_in` 自顶向下逐级收窄，
命中块与单层索引完全一致，并报告 `levels`（跨级数）与 `backoff_ms`
（稀疏空档时回退到最近有效块的毫秒数）。`seek_many` 批量定位与逐个
`seek_in` 完全一致。`index_stats` 报告 `entries`/`levels`/`chunks`。

条目数随扇出增大而下降，且为块数的线性量级（等比级数 ≤ n·fanout/(fanout−1)）。
64 块实测：

| fanout | entries | levels |
|-------:|--------:|-------:|
|      2 |     127 |      7 |
|      4 |      85 |      4 |
|      8 |      73 |      3 |
|     64 |      65 |      2 |

## 自测

```
python -m pytest tests -q          # 24 passed
python -m seekindex.cli data/chunks.json --at 1830 --out hit.json
```

CLI 验收输出（连跑两次 `hit.json` 逐字节一致）：

```
seek t=1830 -> start=1800 offset=1800 backoff=30ms boundary=None entries=3 tiered(levels=2, entries=4)
```

`hit.json` 关键数值：`start_ms=1800`，`offset=1800`，`size=900`，
`backoff_ms=30`，`index_entries=3`，多级索引 `levels=2`、`entries=4`。
