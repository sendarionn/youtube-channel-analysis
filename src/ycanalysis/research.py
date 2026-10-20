"""チャンネルURLだけで新規作成または差分更新と分析を行う

使い方:
    python -m ycanalysis.research https://www.youtube.com/@handle
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from .channel_url import parse_channel_url
from .config import load_channel
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
    ch = load_channel(slug)
    status_path = ch.report_dir / "research_status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {"state": "failed", "missing": []}
    state = status["state"]
    print(f"\n調査状態: {state}")
    if state == "complete":
        print(f"最終報告書: reports/{slug}/FINAL_REPORT.md（品質ゲート通過）")
    else:
        print("自動工程（収集・検証・定量分析・標本選定）まで実行した。調査は未完成")
        print(f"作業用の報告書: reports/{slug}/DRAFT_REPORT.md、自動集計: reports/{slug}/AUTO_DRAFT.md")
        print("AIエージェントが続ける工程（methodology/README.md）:")
        for x in status.get("next_actions", []):
            print(f"  - {x}")
    print(f"グラフ: reports/{slug}/charts/")

if __name__ == "__main__":
    main()
