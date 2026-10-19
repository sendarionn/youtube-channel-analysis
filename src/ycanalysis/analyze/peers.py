"""Phase 4: 類似チャンネルとの比較

各チャンネルの直近 n 本の通常動画（公開7日以上）で比較する
対象チャンネルも同じ条件（直近 n 本）にそろえる

使い方:
    python -m ycanalysis.analyze.peers <main-slug> <peer-slug> [<peer-slug> ...] [--n 40]
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from ..config import load_channel
from ..visualize import style
from ..visualize.contact_sheet import contact_sheet
from ..visualize.style import SERIES, TEXT_2, plt, save
from . import wayback_parse
from .build_dataset import load_videos
from .quant import md_table


def channel_summary(ch, n: int) -> tuple[dict, pd.DataFrame]:
    v, _ = load_videos(ch)
    vid = v[(v["kind"] == "video") & v["mature"]].sort_values("published_at").tail(n)
    page, _ = wayback_parse.build(ch.raw_dir / "channel_page")
    cur = page.iloc[-1]
    span_days = (vid["published_at"].max() - vid["published_at"].min()).total_seconds() / 86400
    jst = vid["published_at"].dt.tz_convert("Asia/Tokyo")
    summary = {
        "チャンネル": ch.name,
        "登録者": cur["subscribers"], "総再生": cur["total_views"], "公開動画数": cur["video_count"],
        "開設日": cur["joined"],
        "比較本数": len(vid),
        "期間": f"{vid['published_jst'].min()[:10]}〜{vid['published_jst'].max()[:10]}",
        "週あたり投稿": len(vid) / max(span_days, 1) * 7,
        "尺中央値(分)": vid["duration_min"].median(),
        "再生中央値": vid["views"].median(),
        "再生/登録者": vid["views"].median() / cur["subscribers"],
        "最大/中央値": vid["views"].max() / vid["views"].median(),
        "高評価率": (vid["likes"] / vid["views"]).median(),
        "コメント率": (vid["comments"] / vid["views"]).median(),
        "タイトル文字数": vid["title_len"].median(),
        "【】率": vid["has_bracket"].mean(),
        "疑問符率": vid["has_question_mark"].mean(),
        "数字率": vid["has_number"].mean(),
        "日本含む率": vid["title"].str.contains("日本").mean(),
        "朝6-8時投稿率": jst.dt.hour.between(6, 7).mean(),
        "Shorts本数(全体)": int((v["kind"] == "short").sum()),
    }
    return summary, vid.assign(channel=ch.name)


def history(ch) -> pd.DataFrame:
    frames = []
    for sub in ("wayback", "channel_page"):
        d = ch.raw_dir / sub
        if d.exists() and list(d.glob("*.html")):
            h, _ = wayback_parse.build(d)
            frames.append(h)
    h = pd.concat(frames).sort_values("snapshot_at").drop_duplicates("snapshot_at")
    return wayback_parse.flag_anomalies(h).assign(channel=ch.name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("main")
    ap.add_argument("peers", nargs="+")
    ap.add_argument("--n", type=int, default=40)
    a = ap.parse_args()
    style.setup()
    main_ch = load_channel(a.main)
    chans = [main_ch] + [load_channel(p) for p in a.peers]
    rows, vids, hists = [], [], []
    for ch in chans:
        s, v = channel_summary(ch, a.n)
        rows.append(s)
        vids.append(v)
        hists.append(history(ch))
    summ = pd.DataFrame(rows).set_index("チャンネル").T
    allv = pd.concat(vids)
    hist = pd.concat(hists)
    out_dir = main_ch.report_dir
    allv[["channel", "video_id", "published_jst", "title", "duration_min", "views", "likes", "comments"]].to_csv(
        main_ch.processed_dir / "peer_videos.csv", index=False)
    hist.to_csv(main_ch.processed_dir / "peer_history.csv", index=False)

    lines = ["# Phase 4 比較表（自動生成）", "", f"各チャンネルの直近 {a.n} 本の通常動画（公開7日以上）", "",
             md_table(summ.reset_index().rename(columns={"index": "指標"}), "{:,.3f}"), "",
             "## 登録者数の観測値（Wayback 月1件 + 直接取得）", ""]
    for name, g in hist.groupby("channel"):
        g = g.dropna(subset=["subscribers"])
        lines += [f"### {name}", "", md_table(g.assign(snapshot_at=g["snapshot_at"].dt.strftime("%Y-%m-%d"))[
            ["snapshot_at", "subscribers", "video_count", "anomaly"]], "{:,.0f}"), ""]
    (out_dir / "phase4_tables.md").write_text("\n".join(lines))

    # 尺と再生数の分布
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    names = [c.name for c in chans]
    for i, name in enumerate(names):
        g = allv[allv["channel"] == name]
        axes[0].scatter(g["duration_min"], np.full(len(g), i) + (np.random.default_rng(i).random(len(g)) - 0.5) * 0.3,
                        s=12, color=SERIES[0] if i else SERIES[1], alpha=0.7, edgecolor="none")
        axes[1].scatter(g["views"], np.full(len(g), i) + (np.random.default_rng(i).random(len(g)) - 0.5) * 0.3,
                        s=12, color=SERIES[0] if i else SERIES[1], alpha=0.7, edgecolor="none")
    for ax in axes:
        ax.set_yticks(range(len(names)), [n[:12] for n in names])
    axes[0].set_title("動画尺（分）")
    axes[1].set_title("再生数（対数軸）")
    axes[1].set_xscale("log")
    save(fig, main_ch.report_dir / "charts" / "09_peers_dist.png")

    # 登録者の推移（開設日からの経過日で揃える）
    fig, ax = plt.subplots(figsize=(9, 4))
    for i, ch in enumerate(chans):
        g = hist[(hist["channel"] == ch.name) & ~hist["anomaly"]].dropna(subset=["subscribers"])
        if ch is main_ch:
            start = pd.Timestamp("2026-02-12", tz="UTC")  # 初投稿日（joined は 2022 だが投稿開始は 2026-02）
        else:
            start = pd.to_datetime(g["joined"].dropna().iloc[0], format="mixed").tz_localize("UTC")
        x = (g["snapshot_at"] - start).dt.days / 30.4
        ax.plot(x, g["subscribers"], marker="o", ms=4, color=SERIES[i], label=ch.name)
    ax.set_xlabel("投稿開始（他チャンネルは開設日）からの経過月数")
    ax.yaxis.set_major_formatter(lambda x, _: f"{x / 10000:.0f}万")
    ax.set_title("登録者数の推移（経過月で比較）")
    ax.legend(frameon=False)
    save(fig, main_ch.report_dir / "charts" / "10_peers_growth.png")

    # サムネイル一覧（直近から再生上位4・下位4）
    for ch in chans[1:]:
        tdir = ch.raw_dir / "thumbnails" / "hqdefault"
        g = allv[allv["channel"] == ch.name].sort_values("views")
        pick = pd.concat([g.tail(4).iloc[::-1], g.head(4)])
        items = [(tdir / f"{r['video_id']}.jpg", f"{r['views'] / 10000:.1f}万回\n{r['title'][:24]}")
                 for _, r in pick.iterrows() if (tdir / f"{r['video_id']}.jpg").exists()]
        if items:
            contact_sheet(items, main_ch.report_dir / "thumbnails" / f"peer_{ch.slug}.jpg", cols=4, cell_w=240)
    print(out_dir / "phase4_tables.md")


if __name__ == "__main__":
    main()
