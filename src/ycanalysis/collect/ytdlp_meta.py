"""yt-dlp による公開メタデータの収集（動画ファイルはダウンロードしない）

YouTube Data API のキーがない場合の取得手段
YouTube のウォッチページに表示される公開情報のみを取得する

使い方:
    python -m ycanalysis.collect.ytdlp_meta <slug> list
    python -m ycanalysis.collect.ytdlp_meta <slug> videos [--resume DIR] [--limit N]
    python -m ycanalysis.collect.ytdlp_meta <slug> thumbnails
    python -m ycanalysis.collect.ytdlp_meta <slug> subs ID [ID ...]
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import requests
import yt_dlp

from ..config import Channel, load_channel
from .rawstore import latest_snapshot_dir, new_snapshot_dir, write_json, write_manifest

TABS = ("videos", "shorts", "streams")

# 動画ごとの JSON から除外する巨大・不要なキー
DROP_KEYS = {
    "formats", "requested_formats", "thumbnails", "automatic_captions", "subtitles",
    "heatmap", "http_headers", "_format_sort_fields", "requested_subtitles",
}


def _opts(channel: Channel, **extra) -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "skip_download": True,
        # 自動翻訳されたタイトルではなく原題を取得する
        "extractor_args": {"youtube": {"lang": [channel.lang]}},
        **extra,
    }


def list_channel(channel: Channel) -> list[dict]:
    """チャンネルの各タブから動画IDを列挙する"""
    out = []
    with yt_dlp.YoutubeDL(_opts(channel, extract_flat="in_playlist")) as ydl:
        for tab in TABS:
            try:
                info = ydl.extract_info(f"https://www.youtube.com/channel/{channel.channel_id}/{tab}", download=False)
            except yt_dlp.utils.DownloadError as e:
                print(f"{tab}: 取得なし ({e})")
                continue
            for e in info.get("entries") or []:
                out.append({"id": e["id"], "tab": tab, "title": e.get("title"),
                            "view_count": e.get("view_count"), "duration": e.get("duration")})
            time.sleep(2)
    return out


def trim_info(info: dict) -> dict:
    d = {k: v for k, v in info.items() if k not in DROP_KEYS}
    d["subtitle_langs"] = sorted((info.get("subtitles") or {}).keys())
    d["auto_caption_has_ja"] = "ja" in (info.get("automatic_captions") or {})
    d["heatmap"] = info.get("heatmap")  # 「最も再生された部分」グラフ（公開されている場合）
    return d


def collect_videos(channel: Channel, resume: Path | None = None, sleep: float = 2.0,
                   limit: int | None = None) -> Path:
    """limit を指定すると各タブの新しい順に limit 本だけ取得する（比較チャンネル用）"""
    if resume:
        d = resume
        listing = json.loads((d / "list.json").read_text())
    else:
        d = new_snapshot_dir(channel.raw_dir, "ytdlp_videos")
        listing = list_channel(channel)
        if limit:
            listing = [x for tab in TABS for x in [e for e in listing if e["tab"] == tab][:limit]]
        write_json(d / "list.json", listing)
        write_manifest(d, source="YouTube 公開ウォッチページ", method="yt-dlp (skip_download)",
                       yt_dlp_version=yt_dlp.version.__version__, channel_id=channel.channel_id,
                       lang=channel.lang, count=len(listing), limit_per_tab=limit)
    vdir = d / "videos"
    vdir.mkdir(exist_ok=True)
    with yt_dlp.YoutubeDL(_opts(channel)) as ydl:
        for i, item in enumerate(listing):
            path = vdir / f"{item['id']}.json"
            if path.exists():
                continue
            try:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={item['id']}", download=False)
            except yt_dlp.utils.DownloadError as e:
                print(f"[{i}] {item['id']} 失敗: {e}")
                continue
            t = trim_info(info)
            t["tab"] = item["tab"]
            t["retrieved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            write_json(path, t)
            print(f"[{i + 1}/{len(listing)}] {item['id']} {t.get('title', '')[:40]}")
            time.sleep(sleep + random.random())
    return d


def collect_thumbnails(channel: Channel, size: str = "hqdefault") -> Path:
    """サムネイル画像を取得する（i.ytimg.com の公開URL）"""
    src = latest_snapshot_dir(channel.raw_dir, "ytdlp_videos")
    ids = [json.loads(p.read_text())["id"] for p in sorted((src / "videos").glob("*.json"))]
    d = channel.raw_dir / "thumbnails" / size
    d.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    for vid in ids:
        path = d / f"{vid}.jpg"
        if path.exists():
            continue
        r = s.get(f"https://i.ytimg.com/vi/{vid}/{size}.jpg", timeout=30)
        if r.ok:
            path.write_bytes(r.content)
        time.sleep(0.3)
    write_manifest(d, source="https://i.ytimg.com/vi/<id>/" + size + ".jpg", method="HTTP GET",
                   from_snapshot=src.name, count=len(list(d.glob("*.jpg"))))
    return d


def collect_subs(channel: Channel, ids: list[str]) -> Path:
    """日本語字幕（手動字幕優先、なければ自動字幕）を取得する"""
    d = channel.raw_dir / "subs"
    d.mkdir(parents=True, exist_ok=True)
    opts = _opts(channel, writesubtitles=True, writeautomaticsub=True, subtitleslangs=["ja", "ja-orig"],
                 subtitlesformat="json3", outtmpl=str(d / "%(id)s.%(ext)s"))
    with yt_dlp.YoutubeDL(opts) as ydl:
        for vid in ids:
            if list(d.glob(f"{vid}.*.json3")):
                continue
            try:
                ydl.download([f"https://www.youtube.com/watch?v={vid}"])
            except yt_dlp.utils.DownloadError as e:
                print(f"{vid} 失敗: {e}")
            time.sleep(3 + random.random())
    write_manifest(d, source="YouTube 字幕トラック", method="yt-dlp writesubtitles/writeautomaticsub json3",
                   count=len(list(d.glob("*.json3"))))
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("cmd", choices=["list", "videos", "thumbnails", "subs"])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--resume", type=Path)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    ch = load_channel(a.slug)
    if a.cmd == "list":
        print(json.dumps(list_channel(ch), ensure_ascii=False, indent=1))
    elif a.cmd == "videos":
        print(collect_videos(ch, a.resume, limit=a.limit))
    elif a.cmd == "thumbnails":
        print(collect_thumbnails(ch))
    elif a.cmd == "subs":
        print(collect_subs(ch, a.ids))


if __name__ == "__main__":
    main()
