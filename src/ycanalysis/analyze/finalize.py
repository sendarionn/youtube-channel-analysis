"""自動生成した草稿を、未検証事項を明示した最終報告書として保存する"""
from __future__ import annotations

import argparse

from ..config import load_channel, record_run


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ch = load_channel(ap.parse_args().slug)
    final = ch.report_dir / "FINAL_REPORT.md"
    if final.exists():
        print("既存のFINAL_REPORT.mdを変更しない")
        return
    draft = ch.report_dir / "DRAFT_REPORT.md"
    if not draft.exists():
        raise SystemExit("DRAFT_REPORT.mdがないため最終報告書を作成できない")
    note = ("# 自動調査の検証状態\n\n"
            "定量分析まで完了\n\n"
            "テーマ分類は自動生成した暫定結果で、人手による一致率検証は未実施\n\n"
            "字幕または映像を取得していない動画の内容は確認済みと扱わない\n\n")
    final.write_text(note + draft.read_text())
    record_run(ch, "finalize", qualitative_validation=False)
    print(final)


if __name__ == "__main__":
    main()
