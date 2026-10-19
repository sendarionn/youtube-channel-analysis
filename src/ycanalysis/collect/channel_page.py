"""現在のチャンネル概要ページ（about）のHTMLを保存する

登録者数・総再生数・動画数・開設日を、Wayback のスナップショットと同じ解析処理で読むため

使い方:
    python -m ycanalysis.collect.channel_page <slug>
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

import requests

from ..config import load_channel

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130 Safari/537.36")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ch = load_channel(ap.parse_args().slug)
    d = ch.raw_dir / "channel_page"
    d.mkdir(parents=True, exist_ok=True)
    # 表示言語を英語に固定し、Wayback スナップショットと同じ表記で解析できるようにする
    r = requests.get(f"https://www.youtube.com/channel/{ch.channel_id}/about",
                     headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}, timeout=60)
    r.raise_for_status()
    path = d / f"{datetime.now(timezone.utc):%Y%m%d%H%M%S}_about.html"
    path.write_bytes(r.content)
    print(path)


if __name__ == "__main__":
    main()
