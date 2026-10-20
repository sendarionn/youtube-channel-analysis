"""報告書の草稿を作る（自動で書ける事実の節だけを埋め、判断が必要な節は「要記入」で残す）

- AUTO_DRAFT.md：毎回作り直す自動集計の草稿
- DRAFT_REPORT.md：AIエージェント・人間が考察を書き込む作業用の報告書。存在しない場合だけ AUTO_DRAFT.md から作り、
  既にあれば上書きしない（書き込んだ考察を消さないため）
- FINAL_REPORT.md：品質ゲートを通過した後に analyze.finalize が DRAFT_REPORT.md から作る

使い方:
    python -m ycanalysis.analyze.draft_report <slug>
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

from .. import METHODOLOGY_VERSION
from ..config import ROOT, load_channel, record_run
from .quant import has_labels


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    a = ap.parse_args()
    ch = load_channel(a.slug)
    v = pd.read_csv(ch.processed_dir / "analysis_videos.csv", parse_dates=["published_at", "retrieved_at"])
    h = pd.read_csv(ch.processed_dir / "channel_history.csv")
    vid = v[v["kind"] == "video"]
    mature = vid[vid["mature"]]
    cur = h.dropna(subset=["subscribers"]).tail(1)
    subs = f"{int(cur['subscribers'].iloc[0]):,}人" if len(cur) else "未取得"
    tv = cur["total_views"].iloc[0] if len(cur) else None
    info = json.loads((ch.processed_dir / "build_info.json").read_text())
    limited = info["videos_source"].get("limit_per_tab")

    summary = "\n".join([
        f"- 【事実】登録者 {subs}、総再生 {f'{int(tv):,}回' if tv == tv and tv is not None else '未取得'}（概要ページ）",
        f"- 【事実】取得した動画 {len(v)} 本（通常 {len(vid)}・Shorts {int((v['kind'] == 'short').sum())}・"
        f"ライブ {int((v['kind'] == 'live').sum())}）" + (f"、各タブ直近 {limited} 本に限定した試験取得" if limited else ""),
        f"- 【事実】公開期間 {vid['published_jst'].min()[:10]}〜{vid['published_jst'].max()[:10]}",
        f"- 【事実】再生数の中央値 {vid['views'].median():,.0f}、最大 {vid['views'].max():,.0f}"
        f"（最大/中央値 {vid['views'].max() / vid['views'].median():.1f}）",
    ])
    top = mature.nlargest(5, "rel_index")
    growth = "相対再生指数の上位5本（公開{}日以上）\n\n".format(ch.get("analysis", "min_age_days", 7)) + "\n".join(
        f"- [{r.title}]({r.url}) {r.views:,}回、指数 {r.rel_index:.2f}" for r in top.itertuples())
    themes = ("テーマ別の集計は phase2_tables.md 3章" if has_labels(ch) else
              "【未実施】annotations/labels_manual.csv がない。methodology/classification.md の手順でテーマを作る")
    duration = f"- 【事実】尺の中央値 {vid['duration_min'].median():.1f}分\n- 詳細は phase2_tables.md 5・6章"
    rob = ch.report_dir / "robustness.md"
    robustness = "reports/{}/robustness.md を参照".format(ch.slug) if rob.exists() else "（未実行）"
    limits = "\n".join([
        "- 視聴維持率・CTR・トラフィック元・登録転換率は公開データにない",
        "- 登録者数の過去値は Wayback の保存状況に依存する（観測点 {} 件）".format(len(h)),
    ] + (["- 試験取得のため、直近の動画だけで集計している。期間・テーマの比較は全動画の取得後に行う"] if limited else []))
    tpl = (ROOT / "templates" / "report.md").read_text()
    text = tpl.format(name=ch.name, url=ch.url, channel_id=ch.channel_id, retrieved=f"{v['retrieved_at'].min():%Y-%m-%d}",
                      version=METHODOLOGY_VERSION, summary=summary, growth=growth, themes=themes, duration=duration,
                      robustness=robustness, limits=limits)
    auto = ch.report_dir / "AUTO_DRAFT.md"
    auto.write_text(text)
    work = ch.report_dir / "DRAFT_REPORT.md"
    if not work.exists():
        work.write_text(text)
        print(f"作成: {work}")
    else:
        print(f"既存の {work.name} は変更しない（自動集計の更新は {auto.name}）")
    record_run(ch, "draft_report")


if __name__ == "__main__":
    main()
