"""調査実行後の方法論レビューを作る"""
from __future__ import annotations

import argparse
import json
from datetime import date

from ..config import ROOT, load_channel, record_run


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ch = load_channel(ap.parse_args().slug)
    runs_path = ch.report_dir / "run_info.json"
    runs = json.loads(runs_path.read_text()) if runs_path.exists() else {}
    failed = [name for name, info in runs.items() if info.get("status") == "failed"]
    manual = (ch.annotations_dir / "labels_manual.csv").exists()
    text = "\n".join([
        f"# {ch.name} 方法論レビュー",
        "",
        f"- 実施日 {date.today().isoformat()}",
        f"- 失敗工程 {', '.join(failed) if failed else 'なし'}",
        f"- テーマ分類 {'人手ラベルを使用' if manual else '自動暫定分類を使用'}",
        "- 成功動画と低実績動画は相対再生指数の上位・下位として集計",
        "- 公開時期は期間別集計と回帰で確認",
        "- CTR、視聴維持率、登録転換率は公開データでは検証不可",
        "",
        "## 改善判断",
        "",
        "- 自動分類の人手一致率が未検証のため、共通方法論への変更は保留",
        "- 今回の実行だけを根拠に方法論バージョンを変更しない",
        "",
    ])
    base = ROOT / "methodology" / "reviews" / f"{date.today().isoformat()}-{ch.slug}-auto.md"
    if base.exists() and base.read_text() == text:
        print(base)
    elif base.exists():
        n = 2
        while base.with_name(f"{base.stem}-{n}.md").exists():
            n += 1
        base = base.with_name(f"{base.stem}-{n}.md")
        base.write_text(text)
        print(base)
    else:
        base.write_text(text)
        print(base)
    record_run(ch, "methodology_review", improvements_adopted=False)


if __name__ == "__main__":
    main()
