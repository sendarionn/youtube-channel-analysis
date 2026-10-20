"""新しいチャンネルの調査を始める

チャンネルURL（@ハンドル・/channel/ID・動画URLのいずれか）から識別情報を取得し、
設定ファイル・データディレクトリ・調査指示書のひな形を作る。既存のファイルは上書きしない

使い方:
    python -m ycanalysis.init <URL> --slug <slug> [--lang ja]
"""
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

import yt_dlp

from . import METHODOLOGY_VERSION
from .config import ROOT

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def resolve(url: str, lang: str) -> dict:
    """URL からチャンネルID・名前・ハンドルを得る（動画一覧は取らない）"""
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": True, "playlist_items": "1",
            "extractor_args": {"youtube": {"lang": [lang]}}}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") or []
    cid = info.get("channel_id") or (entries[0].get("channel_id") if entries else None)
    if not cid:
        raise SystemExit(f"チャンネルIDを特定できない: {url}")
    return {"channel_id": cid, "name": info.get("channel") or info.get("uploader") or info.get("title", ""),
            "handle": info.get("uploader_id") if str(info.get("uploader_id", "")).startswith("@") else ""}


def write_new(path: Path, text: str) -> bool:
    if path.exists():
        print(f"既存のため変更しない: {path.relative_to(ROOT)}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(f"作成: {path.relative_to(ROOT)}")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--slug", required=True, help="英小文字・数字・ハイフン")
    ap.add_argument("--lang", default="ja")
    a = ap.parse_args()
    if not SLUG.match(a.slug):
        raise SystemExit("slug は英小文字・数字・ハイフンのみ")
    info = resolve(a.url, a.lang)
    url = f"https://www.youtube.com/{info['handle']}" if info["handle"] else \
        f"https://www.youtube.com/channel/{info['channel_id']}"
    tpl = (ROOT / "templates" / "channel-config.toml").read_text()
    cfg = tpl.format(slug=a.slug, name=info["name"].replace('"', "'"), handle=info["handle"],
                     channel_id=info["channel_id"], url=url, lang=a.lang)
    lines = [ln for ln in cfg.splitlines() if not ln.startswith(("# python -m ycanalysis.init", "# チャンネル設定のテンプレート"))]
    cfg = f"# {info['name']} の設定（{date.today().isoformat()} に ycanalysis.init で作成）\n" + "\n".join(lines) + "\n"
    write_new(ROOT / "config" / "channels" / f"{a.slug}.toml", cfg)
    for sub in ("raw", "processed", "annotations"):
        (ROOT / "data" / a.slug / sub).mkdir(parents=True, exist_ok=True)
    (ROOT / "reports" / a.slug / "charts").mkdir(parents=True, exist_ok=True)
    brief = (ROOT / "templates" / "analysis-brief.md").read_text().format(
        name=info["name"], url=url, slug=a.slug, date=date.today().isoformat(), version=METHODOLOGY_VERSION)
    write_new(ROOT / "docs" / f"{a.slug}-analysis.md", brief)
    print(f"\n次の手順: methodology/README.md の「新しいチャンネルの調査」を参照\n"
          f"  .venv/bin/python -m ycanalysis.run {a.slug} --collect")


if __name__ == "__main__":
    main()
