"""再生実績と特徴量の関係を検定する小さな関数群"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def compare_binary(df: pd.DataFrame, feature: str, metric: str = "rel_index") -> dict:
    """feature が True/False の群で metric の中央値を比較する（Mann-Whitney U, 両側）"""
    a = df.loc[df[feature].astype(bool), metric].dropna()
    b = df.loc[~df[feature].astype(bool), metric].dropna()
    res = {"feature": feature, "n_true": len(a), "n_false": len(b),
           "median_true": a.median() if len(a) else np.nan, "median_false": b.median() if len(b) else np.nan}
    res["ratio"] = res["median_true"] / res["median_false"] if len(a) and len(b) else np.nan
    if len(a) >= 5 and len(b) >= 5:
        u = stats.mannwhitneyu(a, b, alternative="two-sided")
        res["p"] = u.pvalue
        # 順位双列相関（効果量）: 正なら True 群が高い
        res["rank_biserial"] = 2 * u.statistic / (len(a) * len(b)) - 1
    else:
        res["p"], res["rank_biserial"] = np.nan, np.nan
    return res


def compare_groups(df: pd.DataFrame, group: str, metric: str = "rel_index", min_n: int = 1) -> pd.DataFrame:
    g = df.groupby(group)[metric]
    out = pd.DataFrame({"n": g.size(), "median": g.median(), "mean_log2": df.groupby(group)["log_rel"].mean(),
                        "q25": g.quantile(0.25), "q75": g.quantile(0.75)})
    out = out[out["n"] >= min_n].sort_values("median", ascending=False)
    groups = [df.loc[df[group] == k, metric].dropna() for k in out.index if out.loc[k, "n"] >= 3]
    out.attrs["kruskal_p"] = stats.kruskal(*groups).pvalue if len(groups) >= 2 else np.nan
    return out


def bh_adjust(p: pd.Series) -> pd.Series:
    """Benjamini-Hochberg による多重比較補正"""
    p = p.astype(float)
    mask = p.notna()
    pv = p[mask].to_numpy()
    order = np.argsort(pv)
    ranked = pv[order] * len(pv) / (np.arange(len(pv)) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(len(pv))
    out[order] = np.minimum(ranked, 1)
    res = pd.Series(np.nan, index=p.index)
    res[mask] = out
    return res
