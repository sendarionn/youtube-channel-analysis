"""Phase 3 の内容分析対象を選ぶ

規則:
- 対象: 通常動画・公開7日以上・config の exclude_themes を除く
- 群: 相対再生指数の上位20%（high）、40〜60%（mid）、下位20%（low）
- 各群から期間ごとに per_period 本、同じ期間内でテーマが重複しないように選ぶ
  - high は指数の高い順、low は低い順、mid は中央値に近い順に候補を並べる
- 期間内の候補が足りない場合は、他期間の候補で補う

使い方:
    python -m ycanalysis.analyze.select_sample <slug> [--per-period 3]
"""
from __future__ import annotations

import argparse

import pandas as pd


def pick(cands: pd.DataFrame, n: int) -> list[int]:
    chosen, themes = [], set()
    for idx, r in cands.iterrows():
        if r["theme"] in themes:
            continue
        chosen.append(idx)
        themes.add(r["theme"])
        if len(chosen) == n:
            return chosen
    # テーマ重複を許して補う
    for idx in cands.index:
        if idx not in chosen:
            chosen.append(idx)
        if len(chosen) == n:
            break
    return chosen


def select(v: pd.DataFrame, per_period: int = 3, exclude_themes=()) -> pd.DataFrame:
    pool = v[(v["kind"] == "video") & v["mature"] & ~v["theme"].isin(exclude_themes)].copy()
    q = pool["rel_index"].quantile([0.2, 0.4, 0.6, 0.8])
    med = pool["rel_index"].median()
    tiers = {
        "high": pool[pool["rel_index"] >= q[0.8]].sort_values("rel_index", ascending=False),
        "mid": pool[pool["rel_index"].between(q[0.4], q[0.6])].assign(d=lambda x: (x["rel_index"] - med).abs()).sort_values("d"),
        "low": pool[pool["rel_index"] <= q[0.2]].sort_values("rel_index"),
    }
    rows = []
    periods = sorted(pool["period"].unique())
    for tier, cands in tiers.items():
        picked: list[int] = []
        for p in periods:
            picked += pick(cands[cands["period"] == p], per_period)
        rest = cands.drop(index=picked)
        picked += pick(rest, per_period * len(periods) - len(picked)) if len(picked) < per_period * len(periods) else []
        rows.append(pool.loc[picked].assign(tier=tier))
    return pd.concat(rows)


def main() -> None:
    from ..config import load_channel
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--per-period", type=int, default=3)
    a = ap.parse_args()
    ch = load_channel(a.slug)
    v = pd.read_csv(ch.processed_dir / "analysis_videos.csv")
    s = select(v, a.per_period, ch.get("analysis", "exclude_themes", []))
    cols = ["tier", "period", "theme", "video_id", "published_jst", "duration_min", "views", "rel_index", "title"]
    s[cols].to_csv(ch.processed_dir / "phase3_sample.csv", index=False)
    print(s[cols].to_string())


if __name__ == "__main__":
    main()
