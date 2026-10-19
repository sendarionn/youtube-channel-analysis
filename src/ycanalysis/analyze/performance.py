"""公開時期の違いを考慮した再生実績指標

公開後7日・30日の再生数は公開データから取得できないため、次の指標で代替する
- rel_index: 同一動画種別の前後 window 本（公開順）の再生数中央値に対する比率
  チャンネル規模の時期差と、累計期間の差の一部を吸収する
- views_per_day: 累計再生数 / 公開からの経過日数（新しい動画ほど過大になりやすい）
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def neighbor_median(values: pd.Series, window: int = 10) -> pd.Series:
    """各要素について、自身を除く前後 window 本の中央値を返す（端は片側で補う）"""
    v = values.to_numpy(dtype=float)
    out = np.empty(len(v))
    for i in range(len(v)):
        lo, hi = max(0, i - window), min(len(v), i + window + 1)
        neigh = np.concatenate([v[lo:i], v[i + 1:hi]])
        out[i] = np.median(neigh) if len(neigh) else np.nan
    return pd.Series(out, index=values.index)


def add_performance(df: pd.DataFrame, window: int = 10, min_age_days: int = 7) -> pd.DataFrame:
    """df は published_at, views, age_days, kind を持つこと"""
    df = df.sort_values("published_at").copy()
    df["views_per_day"] = df["views"] / df["age_days"].clip(lower=1)
    df["rel_index"] = np.nan
    for kind, g in df.groupby("kind"):
        med = neighbor_median(g["views"], window)
        df.loc[g.index, "rel_index"] = g["views"] / med
    df["log_rel"] = np.log2(df["rel_index"])
    # 公開直後の動画は再生数が確定していないため、比較対象から外すフラグ
    df["mature"] = df["age_days"] >= min_age_days
    return df


def assign_tier(rel: pd.Series, hi_q: float = 0.8, lo_q: float = 0.2) -> pd.Series:
    """rel_index の分位で high / mid / low に分ける"""
    hi, lo = rel.quantile(hi_q), rel.quantile(lo_q)
    return pd.Series(np.where(rel >= hi, "high", np.where(rel <= lo, "low", "mid")), index=rel.index)
