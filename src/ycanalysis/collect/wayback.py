"""Internet Archive (Wayback Machine) からチャンネルページの過去スナップショットを取得する

過去の登録者数・動画一覧の再生数を復元するための補完手段
取得したHTMLはそのまま raw/wayback/ に保存し、解析は analyze 側で行う

使い方:
    python -m ycanalysis.collect.wayback <slug> [--monthly]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import quote

import requests

from ..config import Channel, load_channel
from .rawstore import utc_now, write_json

CDX = "https://web.archive.org/cdx/search/cdx"
UA = {"User-Agent": "youtube-channel-analysis research (low-rate)"}


def url_patterns(channel: Channel) -> list[str]:
    pats = [f"www.youtube.com/channel/{channel.channel_id}*"]
    if channel.handle:
        pats.append(f"www.youtube.com/{quote(channel.handle, safe='@')}*")
    return pats


def cdx_query(pattern: str, retries: int = 4, monthly: bool = False) -> list[dict]:
    params = {"url": pattern, "output": "json", "fl": "timestamp,original,statuscode,mimetype",
              "filter": "statuscode:200"}
    if monthly:
        # 各月の最初のスナップショットだけにする（大規模チャンネルの取得量を抑える）
        params["collapse"] = "timestamp:6"
    for i in range(retries):
        try:
            r = requests.get(CDX, params=params, headers=UA, timeout=90)
            if r.ok and r.text.startswith("["):
                rows = r.json()
                return [dict(zip(rows[0], row)) for row in rows[1:]] if rows else []
        except requests.RequestException:
            pass
        time.sleep(10 * (i + 1))
    raise RuntimeError(f"CDX 取得失敗: {pattern}")


def wanted(original: str) -> bool:
    """トップ・videos・about のみ対象にする（shorts/community/playlists は除外）"""
    parts = original.split("youtube.com/", 1)[1].split("?")[0].strip("/").split("/")
    base = 2 if parts[0] == "channel" else 1
    tab = parts[base] if len(parts) > base else ""
    return len(parts) <= base + 1 and tab in ("", "videos", "about", "featured")


def collect(channel: Channel, monthly: bool = False) -> Path:
    d = channel.raw_dir / "wayback"
    d.mkdir(parents=True, exist_ok=True)
    index = []
    for pat in url_patterns(channel):
        index += cdx_query(pat, monthly=monthly)
        time.sleep(3)
    write_json(d / f"cdx_{utc_now().replace(':', '')}.json", index)
    s = requests.Session()
    for row in index:
        if not wanted(row["original"]) or "html" not in row.get("mimetype", "html"):
            continue
        name = f"{row['timestamp']}_{quote(row['original'].split('youtube.com/', 1)[1], safe='')[:120]}.html"
        path = d / name
        if path.exists():
            continue
        # id_ を付けると Wayback のツールバーを含まない元HTMLが返る
        url = f"https://web.archive.org/web/{row['timestamp']}id_/{row['original']}"
        for i in range(3):
            try:
                r = s.get(url, headers=UA, timeout=120)
                if r.ok:
                    path.write_bytes(r.content)
                    print("saved", name, len(r.content))
                    break
            except requests.RequestException:
                pass
            time.sleep(10 * (i + 1))
        time.sleep(4)
    (d / "manifest.json").write_text(json.dumps({
        "source": "Internet Archive Wayback Machine", "method": "CDX API + id_ raw snapshot",
        "patterns": url_patterns(channel), "updated_at": utc_now()}, ensure_ascii=False, indent=2))
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--monthly", action="store_true", help="月1件に間引く")
    a = ap.parse_args()
    print(collect(load_channel(a.slug), monthly=a.monthly))


if __name__ == "__main__":
    main()
