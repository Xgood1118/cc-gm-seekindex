# -*- coding: utf-8 -*-
"""命令行验收入口：

    python -m seekindex.cli data/chunks.json --at 1830 --out hit.json
"""

import argparse
import json
import sys

import seekindex as m


def main(argv=None):
    ap = argparse.ArgumentParser(description="字节索引与精确 seek")
    ap.add_argument("chunks", help="块描述 JSON，如 data/chunks.json")
    ap.add_argument("--at", type=int, required=True, help="请求时刻（毫秒）")
    ap.add_argument("--out", required=True, help="命中结果输出路径")
    ap.add_argument("--max-backoff", type=int, default=None,
                    help="回退偏差上限（毫秒），超限报错")
    ap.add_argument("--fanout", type=int, default=8, help="多级索引扇出")
    a = ap.parse_args(argv)

    chunks = m.load_chunks(a.chunks)
    idx = m.build_index(chunks, max_backoff_ms=a.max_backoff)
    try:
        hit = m.seek_time(idx, a.at)
    except m.SeekError as e:
        print("seek 失败: %s" % e, file=sys.stderr)
        return 2

    tiered = m.build_tiered_index(chunks, fanout=a.fanout)
    t_hit = m.seek_in(tiered, a.at)
    t_stats = m.index_stats(tiered)

    out = {
        "t_ms": a.at,
        "start_ms": hit["start_ms"],
        "end_ms": hit["end_ms"],
        "offset": hit["offset"],
        "size": hit["size"],
        "delta_ms": hit["backoff_ms"],
        "backoff_ms": hit["backoff_ms"],
        "boundary": hit["boundary"],
        "index_entries": len(idx),
        "tiered_block": t_hit["block"],
        "tiered_levels": t_hit["levels"],
        "tiered_entries": t_stats["entries"],
        "ok": True,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print("seek t=%d -> start=%d offset=%d backoff=%dms boundary=%s "
          "entries=%d tiered(levels=%d, entries=%d)"
          % (a.at, hit["start_ms"], hit["offset"], hit["backoff_ms"],
             hit["boundary"], len(idx), t_hit["levels"], t_stats["entries"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
