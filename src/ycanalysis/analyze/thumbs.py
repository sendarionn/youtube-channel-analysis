"""サムネイルの特徴量計算と一覧画像の生成

使い方:
    python -m ycanalysis.analyze.thumbs <slug>
出力:
- processed/thumbnail_features.csv
- reports/<slug>/thumbnails/*.jpg（一覧画像）
- reports/<slug>/thumbnail_tables.md
"""
from __future__ import annotations

import argparse

import pandas as pd

from ..config import load_channel
from ..visualize.contact_sheet import contact_sheet
from .quant import md_table
from .stats import bh_adjust
from .thumbnail_features import features_for_dir

FEATS = ["brightness", "saturation", "colorfulness", "edge_density", "yellow_ratio", "orange_ratio",
         "red_ratio", "blue_ratio", "text_like_ratio"]


def label(r) -> str:
    return f"{r['published_jst'][:10]} 指数{r['rel_index']:.2f}\n{r['title'][:24]}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ch = load_channel(ap.parse_args().slug)
    tdir = ch.raw_dir / "thumbnails" / "hqdefault"
    f = pd.DataFrame(features_for_dir(tdir))
    f.to_csv(ch.processed_dir / "thumbnail_features.csv", index=False)

    v = pd.read_csv(ch.processed_dir / "analysis_videos.csv")
    v = v[(v["kind"] == "video") & v["mature"]].merge(f, on="video_id")
    content = v[~v["theme"].isin(ch.get("analysis", "exclude_themes", []))]
    out_dir = ch.report_dir / "thumbnails"
    path = lambda vid: tdir / f"{vid}.jpg"  # noqa: E731

    top = content.nlargest(24, "rel_index")
    bottom = content.nsmallest(24, "rel_index")
    contact_sheet([(path(r["video_id"]), label(r)) for _, r in top.iterrows()], out_dir / "top24.jpg", cols=6, cell_w=240)
    contact_sheet([(path(r["video_id"]), label(r)) for _, r in bottom.iterrows()], out_dir / "bottom24.jpg", cols=6, cell_w=240)

    # 月ごとに高・中・低を1本ずつ（デザインの変遷を見る）
    rows = []
    for _, g in content.sort_values("published_at").groupby("month"):
        g = g.sort_values("rel_index")
        rows += [g.iloc[-1], g.iloc[len(g) // 2], g.iloc[0]]
    contact_sheet([(path(r["video_id"]), f"{r['month']} " + ["高", "中", "低"][i % 3] + f" {r['rel_index']:.2f}\n{r['title'][:24]}")
                   for i, r in enumerate(rows)], out_dir / "by_month.jpg", cols=3, cell_w=240)

    # 上位20%と下位20%の客観特徴の比較（期間の交絡を避けるため P3・P4 に限定した結果も併記）
    from scipy import stats
    lines = ["# サムネイル客観特徴（自動生成）", ""]
    periods = sorted(content["period"].dropna().unique())
    late = periods[-2:]
    # 見出しは実際の期間ラベルから作る（節目で区切った場合は「5万〜」など、4等分なら「公開日3/4」など）
    late_name = "・".join(p.split()[0] for p in late) + "（" + "、".join(p.split(" ", 1)[-1] for p in late) + "）"
    for name, sub in [("全期間", content), (late_name, content[content["period"].isin(late)])]:
        hi, lo = sub["rel_index"].quantile(0.8), sub["rel_index"].quantile(0.2)
        a, b = sub[sub["rel_index"] >= hi], sub[sub["rel_index"] <= lo]
        res = []
        for c in FEATS:
            p = stats.mannwhitneyu(a[c], b[c]).pvalue
            rho = stats.spearmanr(sub[c], sub["rel_index"]).statistic
            res.append({"特徴": c, "上位20%中央値": a[c].median(), "下位20%中央値": b[c].median(), "p": p,
                        "全体Spearman": rho})
        res = pd.DataFrame(res)
        res["p_bh"] = bh_adjust(res["p"])
        lines += [f"## {name}（上位 {len(a)} 本 / 下位 {len(b)} 本）", "", md_table(res, "{:.3f}"), ""]
    (ch.report_dir / "thumbnail_tables.md").write_text("\n".join(lines))
    print(out_dir)


if __name__ == "__main__":
    main()
