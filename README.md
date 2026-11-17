# 字节索引与精确 seek

一个能按字节索引定位、并给出精确落点误差的 seek 定位器

## 保留签名

- `Chunk`
- `build_index(chunks)`
- `seek_time(index, t_ms)`
- `nearest_key(index, t_ms)`

## 自测

```
python -m pytest tests -q
python -m seekindex.cli data/chunks.json --at 1830 --out hit.json
```
