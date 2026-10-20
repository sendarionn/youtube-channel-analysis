"""新しいチャンネルの調査を始める

チャンネルURL（@ハンドル・/channel/ID・動画URLのいずれか）から識別情報を取得し、
設定ファイル・データディレクトリ・調査指示書のひな形を作る。既存のファイルは上書きしない

使い方:
    python -m ycanalysis.init <URL> --slug <slug> [--lang ja]
"""
from __future__ import annotations

import argparse
import re
import tomllib
from datetime import date
from pathlib import Path

import yt_dlp

from . import METHODOLOGY_VERSION
from .config import ROOT
from .channel_url import parse_channel_url

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def resolve(url: str, lang: str) -> dict:
    """URL からチャンネルID・名前・ハンドルを得る（動画一覧は取らない）"""
    url = parse_channel_url(url).canonical
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


def find_existing(channel_id: str) -> str | None:
    """チャンネルIDが一致する既存設定のslugを返す"""
    for path in sorted((ROOT / "config" / "channels").glob("*.toml")):
        if path.name.endswith(".peers.toml"):
            continue
        with path.open("rb") as f:
            data = tomllib.load(f)
        if data.get("channel_id") == channel_id:
            return data.get("slug", path.stem)
    return None


def suggested_slug(info: dict) -> str:
    handle = str(info.get("handle", "")).lstrip("@").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", handle).strip("-")
    return slug or f"channel-{info['channel_id'][-8:].lower()}"


def initialize(url: str, slug: str | None = None, lang: str = "ja") -> tuple[str, bool]:
    parsed = parse_channel_url(url)
    info = resolve(parsed.canonical, lang)
    existing = find_existing(info["channel_id"])
    if existing:
        print(f"既存の調査を使用: {existing}")
        return existing, False
    slug = slug or suggested_slug(info)
    if not SLUG.match(slug):
        raise ValueError("slug は英小文字・数字・ハイフンのみ")
    url = f"https://www.youtube.com/{info['handle']}" if info["handle"] else \
        f"https://www.youtube.com/channel/{info['channel_id']}"
    tpl = (ROOT / "templates" / "channel-config.toml").read_text()
    cfg = tpl.format(slug=slug, name=info["name"].replace('"', "'"), handle=info["handle"],
                     channel_id=info["channel_id"], url=url, lang=lang)
    lines = [ln for ln in cfg.splitlines() if not ln.startswith(("# python -m ycanalysis.init", "# チャンネル設定のテンプレート"))]
    cfg = f"# {info['name']} の設定（{date.today().isoformat()} に ycanalysis.init で作成）\n" + "\n".join(lines) + "\n"
    write_new(ROOT / "config" / "channels" / f"{slug}.toml", cfg)
    for sub in ("raw", "processed", "annotations"):
        (ROOT / "data" / slug / sub).mkdir(parents=True, exist_ok=True)
    (ROOT / "reports" / slug / "charts").mkdir(parents=True, exist_ok=True)
    brief = (ROOT / "templates" / "analysis-brief.md").read_text().format(
        name=info["name"], url=url, slug=slug, date=date.today().isoformat(), version=METHODOLOGY_VERSION)
    write_new(ROOT / "docs" / f"{slug}-analysis.md", brief)
    return slug, True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--slug", help="省略時はハンドルまたはチャンネルIDから生成")
    ap.add_argument("--lang", default="ja")
    a = ap.parse_args()
    try:
        slug, _ = initialize(a.url, a.slug, a.lang)
    except ValueError as e:
        raise SystemExit(str(e)) from e
    print(f"\n次の手順: methodology/README.md の「新しいチャンネルの調査」を参照\n"
          f"  .venv/bin/python -m ycanalysis.run {slug} --collect")


if __name__ == "__main__":
    main()
