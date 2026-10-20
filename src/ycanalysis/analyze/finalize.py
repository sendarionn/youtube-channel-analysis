"""品質ゲートを通過した DRAFT_REPORT.md を FINAL_REPORT.md にする

- research_status.json の状態が complete でなければ作らない
- 既存の FINAL_REPORT.md と内容が違う場合は reports/<slug>/archive/ に退避してから書く

使い方:
    python -m ycanalysis.analyze.finalize <slug>
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone

from ..config import load_channel, record_run
from .quality_gate import evaluate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ch = load_channel(ap.parse_args().slug)
    status = evaluate(ch.slug)  # 直前の状態ではなく、その時点の成果物で判定する
    if status["state"] != "complete":
        print(f"品質ゲート未通過（{status['state']}）のため FINAL_REPORT.md を作らない")
        print("未通過: " + ", ".join(status["missing"]))
        record_run(ch, "finalize", status="skipped_quality_gate", missing=status["missing"])
        return
    draft = ch.report_dir / "DRAFT_REPORT.md"
    final = ch.report_dir / "FINAL_REPORT.md"
    text = draft.read_text()
    if final.exists():
        if final.read_text() == text:
            print("FINAL_REPORT.md は最新")
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        arch = ch.report_dir / "archive" / f"FINAL_REPORT-{stamp}.md"
        arch.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(final, arch)
        print(f"既存の最終報告書を退避: {arch}")
    final.write_text(text)
    record_run(ch, "finalize", status="complete")
    print(final)


if __name__ == "__main__":
    main()
