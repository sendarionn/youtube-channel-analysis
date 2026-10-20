"""調査実行後の自動の実行記録（方法論レビューの材料）

工程の失敗、品質ゲートの結果、分類の検証状況を、記録されたファイルから書き出す
改善案の検証と採否の判断は AIエージェント・人間が methodology/reviews/<日付>-<slug>.md に書く（methodology/evaluation.md）

出力: methodology/reviews/<日付>-<slug>-auto.md（同じ日の同じ内容なら上書きしない）
"""
from __future__ import annotations

import argparse
import json
from datetime import date

from ..config import ROOT, load_channel, record_run


def _load(path):
    return json.loads(path.read_text()) if path.exists() else {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ch = load_channel(ap.parse_args().slug)
    runs = _load(ch.report_dir / "run_info.json")
    status = _load(ch.report_dir / "research_status.json")
    tv = _load(ch.annotations_dir / "theme_validation.json")
    failed = [name for name, info in runs.items() if name.startswith("run:") and info.get("status") == "failed"]
    if (ch.annotations_dir / "labels_manual.csv").exists():
        theme = "手作業ラベル（labels_manual.csv）"
    elif (ch.annotations_dir / "labels_semantic.csv").exists():
        theme = "設定の規則による分類（labels_semantic.csv）"
    else:
        theme = "反復語による暫定分類（labels_auto.csv）"
    if tv.get("n_checked"):
        theme_check = f"盲検の再判定 {tv['n_checked']} 本、κ={tv.get('kappa')}、一致率={tv.get('agreement')}"
    else:
        theme_check = "未検証（ycanalysis.annotate で盲検の再判定が必要）"
    text = "\n".join([
        f"# {ch.name} 実行記録（自動）",
        "",
        "改善案の検証と採否は、別の方法論レビュー（人間・AIエージェントが作成）に書く",
        "",
        f"- 作成日 {date.today().isoformat()}",
        f"- 調査状態 {status.get('state', '未判定')}（品質ゲートの未通過：{', '.join(status.get('missing', [])) or 'なし'}）",
        f"- 失敗した自動工程 {', '.join(failed) if failed else 'なし'}",
        f"- テーマ分類 {theme}",
        f"- テーマ分類の検証 {theme_check}",
        "- 視聴維持率・CTR・登録転換率は公開データでは検証できない",
        "",
    ])
    base = ROOT / "methodology" / "reviews" / f"{date.today().isoformat()}-{ch.slug}-auto.md"
    if not (base.exists() and base.read_text() == text):
        base.write_text(text)
    print(base)
    record_run(ch, "methodology_review", state=status.get("state"))


if __name__ == "__main__":
    main()
