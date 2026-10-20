"""標準工程の一括実行（methodology/README.md の工程2〜7・11の自動部分）

各工程を別プロセスで実行し、失敗しても後続の独立した工程は続ける
結果は reports/<slug>/run_info.json に記録する

使い方:
    python -m ycanalysis.run <slug> --collect [--limit N] [--no-wayback]   # 収集から
    python -m ycanalysis.run <slug>                                        # 収集済みデータの分析のみ
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time

import json
from datetime import datetime, timezone

from .config import ROOT, load_channel, record_run

PY = sys.executable

# (工程名, コマンド, 依存する工程)
ANALYZE = [
    ("build_dataset", ["-m", "ycanalysis.analyze.build_dataset"], []),
    ("auto_themes", ["-m", "ycanalysis.analyze.auto_themes"], ["build_dataset"]),
    ("quant", ["-m", "ycanalysis.analyze.quant"], ["build_dataset", "auto_themes"]),
    ("thumbs", ["-m", "ycanalysis.analyze.thumbs"], ["quant"]),
    ("robustness", ["-m", "ycanalysis.analyze.robustness"], ["quant"]),
    ("select_sample", ["-m", "ycanalysis.analyze.select_sample"], ["quant"]),
    ("hypothesis_test", ["-m", "ycanalysis.analyze.hypothesis_test"], ["select_sample"]),
    ("draft_report", ["-m", "ycanalysis.analyze.draft_report"], ["quant"]),
    ("methodology_review", ["-m", "ycanalysis.analyze.review"], ["quant"]),
    ("quality_gate", ["-m", "ycanalysis.analyze.quality_gate"], ["draft_report"]),
    ("finalize", ["-m", "ycanalysis.analyze.finalize"], ["quality_gate"]),
]


def collect_steps(limit: int | None, wayback: bool) -> list:
    videos = ["-m", "ycanalysis.collect.ytdlp_meta", "{slug}", "videos"] + (["--limit", str(limit)] if limit else [])
    steps = [("collect_videos", videos, []),
             ("collect_thumbnails", ["-m", "ycanalysis.collect.ytdlp_meta", "{slug}", "thumbnails"], ["collect_videos"]),
             ("collect_channel_page", ["-m", "ycanalysis.collect.channel_page", "{slug}"], [])]
    if wayback:
        steps.append(("collect_wayback", ["-m", "ycanalysis.collect.wayback", "{slug}", "--monthly"], []))
    return steps


def _snapshot(dirs) -> dict:
    return {p: p.stat().st_mtime for d in dirs if d.exists() for p in d.rglob("*") if p.is_file()}


def record_step(ch, name: str, info: dict) -> None:
    """research_status.json の steps に工程の実行記録（開始・終了・結果・変更ファイル・理由）を残す"""
    path = ch.report_dir / "research_status.json"
    st = json.loads(path.read_text()) if path.exists() else {"slug": ch.slug, "state": "collecting"}
    st.setdefault("steps", {})[name] = info
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(st, ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--limit", type=int, help="収集時に各タブの新しい順に N 本だけ取得（試験調査用）")
    ap.add_argument("--no-wayback", action="store_true")
    a = ap.parse_args()
    ch = load_channel(a.slug)
    steps = (collect_steps(a.limit, not a.no_wayback) if a.collect else []) + \
        [(n, c + [a.slug], d) for n, c, d in ANALYZE]
    watch = [ch.raw_dir, ch.processed_dir, ch.report_dir]
    status: dict[str, str] = {}
    for name, cmd, deps in steps:
        cmd = [x.replace("{slug}", a.slug) for x in cmd]
        started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if any(status.get(d) != "ok" for d in deps if d in status):
            status[name] = "skipped"
            print(f"[skip] {name}（依存する工程が失敗）")
            record_step(ch, name, {"status": "skipped", "started_at": started, "ended_at": started,
                                   "reason": "依存する工程が失敗: " + ", ".join(d for d in deps if status.get(d) != "ok")})
            continue
        before = _snapshot(watch)
        t0 = time.time()
        r = subprocess.run([PY, *cmd], capture_output=True, text=True)
        status[name] = "ok" if r.returncode == 0 else "failed"
        after = _snapshot(watch)
        changed = sorted(str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
                         for p, m in after.items() if before.get(p) != m)
        print(f"[{status[name]}] {name} {time.time() - t0:.0f}秒")
        if r.returncode != 0:
            print("  " + "\n  ".join(r.stderr.strip().splitlines()[-5:]))
        tail = r.stderr.strip().splitlines()[-3:] if r.returncode else []
        record_run(ch, f"run:{name}", status=status[name], seconds=round(time.time() - t0, 1), stderr_tail=tail)
        record_step(ch, name, {"status": status[name], "started_at": started,
                               "ended_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "command": " ".join(cmd), "outputs": changed[:50], "n_outputs": len(changed),
                               "reason": " / ".join(tail)})
    failed = [k for k, v in status.items() if v != "ok"]
    st = json.loads((ch.report_dir / "research_status.json").read_text())
    print(f"\n自動工程: {'すべて成功' if not failed else '失敗・未実行あり ' + ', '.join(failed)}")
    print(f"調査状態: {st.get('state')}（自動工程の成功は調査の完成を意味しない）")
    for x in st.get("next_actions", []):
        print(f"  次: {x}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
