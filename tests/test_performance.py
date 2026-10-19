import pandas as pd

from ycanalysis.analyze.performance import add_performance, assign_tier, neighbor_median


def test_neighbor_median_excludes_self():
    s = pd.Series([1, 1, 100, 1, 1])
    m = neighbor_median(s, window=2)
    assert m.iloc[2] == 1


def test_rel_index_detects_outlier_and_separates_kind():
    df = pd.DataFrame({
        "published_at": pd.date_range("2025-01-01", periods=7),
        "views": [100, 100, 1000, 100, 100, 5, 5],
        "age_days": [30] * 7,
        "kind": ["video"] * 5 + ["short"] * 2,
    })
    out = add_performance(df, window=2)
    assert out.loc[2, "rel_index"] == 10
    assert out.loc[5, "rel_index"] == 1  # Shorts は Shorts 同士で比較される


def test_assign_tier():
    t = assign_tier(pd.Series(range(10)), 0.8, 0.2)
    assert list(t[:2]) == ["low", "low"]
    assert list(t[-2:]) == ["high", "high"]


def test_compare_binary_and_bh():
    import numpy as np
    from ycanalysis.analyze.stats import bh_adjust, compare_binary
    df = pd.DataFrame({"f": [True] * 10 + [False] * 10, "rel_index": list(range(10, 20)) + list(range(10))})
    r = compare_binary(df, "f")
    assert r["ratio"] > 1 and r["rank_biserial"] == 1 and r["p"] < 0.01
    adj = bh_adjust(pd.Series([0.01, 0.04, np.nan, 0.03]))
    assert np.isnan(adj[2]) and abs(adj[0] - 0.03) < 1e-9 and abs(adj[3] - 0.04) < 1e-9
