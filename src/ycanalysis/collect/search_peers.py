"""比較対象チャンネルの候補を YouTube 検索結果から収集する

対象チャンネルの主要テーマを検索語にし、上位結果に頻出するチャンネルを候補とする
検索語は config/channels/<slug>.toml の peer_queries に置く

使い方:
    python -m ycanalysis.collect.search_peers <slug> [--n 30]
"""
from __future__ import annotations

import argparse
import time
import tomllib

import yt_dlp

from ..config import ROOT, load_channel
from .rawstore import new_snapshot_dir, write_json, write_manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args()
    ch = load_channel(a.slug)
    with (ROOT / "config" / "channels" / f"{a.slug}.peers.toml").open("rb") as f:
        queries = tomllib.load(f)["queries"]
    d = new_snapshot_dir(ch.raw_dir, "peer_search")
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True,
            "extractor_args": {"youtube": {"lang": [ch.lang]}}}
    results = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        for q in queries:
            info = ydl.extract_info(f"ytsearch{a.n}:{q}", download=False)
            for rank, e in enumerate(info.get("entries") or [], 1):
                results.append({"query": q, "rank": rank, "video_id": e.get("id"), "title": e.get("title"),
                                "channel": e.get("channel"), "channel_id": e.get("channel_id"),
                                "views": e.get("view_count"), "duration": e.get("duration")})
            time.sleep(3)
    write_json(d / "results.json", results)
    write_manifest(d, source="YouTube 検索結果", method=f"yt-dlp ytsearch{a.n}（ログインなし・地域は取得環境依存）",
                   queries=queries)
    print(d)


if __name__ == "__main__":
    main()
