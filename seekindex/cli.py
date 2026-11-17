# -*- coding: utf-8 -*-
"""命令行：python -m seekindex.cli data/chunks.json --at 1830 --out hit.json"""

import argparse
import json

import seekindex as m


def main():
    ap = argparse.ArgumentParser(description="字节索引与精确 seek")
    ap.add_argument("chunks", help="chunk 列表 JSON 路径")
    ap.add_argument("--at", type=int, required=True, help="请求时刻（毫秒）")
    ap.add_argument("--out", required=True, help="落点结果输出路径")
    ap.add_argument("--max-delta", type=int, default=m.DEFAULT_MAX_DELTA_MS,
                    help="回退偏差上限（毫秒），默认 %(default)s")
    a = ap.parse_args()

    chunks = m.load_chunks(a.chunks)
    index = m.build_index(chunks)
    hit = m.seek_time(index, a.at, max_delta_ms=a.max_delta)

    result = dict(hit)
    result["index_entries"] = len(index)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
