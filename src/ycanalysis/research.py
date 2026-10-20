"""チャンネルURLだけで新規作成または差分更新と分析を行う

使い方:
    python -m ycanalysis.research https://www.youtube.com/@handle
"""
from __future__ import annotations

import argparse
import subprocess
import sys

from .channel_url import parse_channel_url
from .init import initialize


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--slug")
    ap.add_argument("--lang", default="ja")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-wayback", action="store_true")
    a = ap.parse_args()
    try:
        parsed = parse_channel_url(a.url)
        slug, created = initialize(parsed.canonical, a.slug, a.lang)
    except ValueError as e:
        raise SystemExit(str(e)) from e
    cmd = [sys.executable, "-m", "ycanalysis.run", slug, "--collect"]
    if a.limit:
        cmd += ["--limit", str(a.limit)]
    if a.no_wayback:
        cmd.append("--no-wayback")
    print(f"{'新規調査' if created else '既存調査の更新'}: {slug}")
    result = subprocess.run(cmd)
    if result.returncode:
        raise SystemExit(f"調査に失敗しました  run_info.jsonで工程別の原因を確認してください  slug={slug}")
    print(f"分析完了: reports/{slug}/FINAL_REPORT.md")
    print(f"グラフ: reports/{slug}/charts/")


if __name__ == "__main__":
    main()
