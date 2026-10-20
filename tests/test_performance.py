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


def test_assign_period_fallback_and_labels():
    import numpy as np
    from ycanalysis.analyze.quant import assign_period
    v = pd.DataFrame({"published_at": pd.date_range("2026-01-01", periods=8, tz="UTC")})
    v["pub_jst"] = v["published_at"]
    p = assign_period(v, pd.DataFrame(columns=["subs_claimed", "pub_jst"]), [10000])
    assert p.nunique() == 4 and p.iloc[0].startswith("P1") and p.iloc[-1].startswith("P4")
    ms = pd.DataFrame({"subs_claimed": [10000, 50000], "pub_jst": [v["pub_jst"][2], v["pub_jst"][5]]})
    p = assign_period(v, ms, [10000, 50000, 100000])
    assert list(p) == ["P1 〜1万"] * 2 + ["P2 1万〜5万"] * 3 + ["P3 5万〜"] * 3


def test_assign_period_fallback_uses_regular_videos_only():
    from ycanalysis.analyze.quant import assign_period
    v = pd.DataFrame({"published_at": pd.date_range("2026-01-01", periods=12, tz="UTC"),
                      "kind": ["short"] * 4 + ["video"] * 8})
    v["pub_jst"] = v["published_at"]
    p = assign_period(v, pd.DataFrame(columns=["subs_claimed", "pub_jst"]), [])
    assert set(p[v["kind"] == "video"].str[:2]) == {"P1", "P2", "P3", "P4"}
