import pandas as pd

from ycanalysis.analyze.select_sample import pick, select


def test_pick_prefers_distinct_themes():
    c = pd.DataFrame({"theme": ["A", "A", "B", "C"]})
    assert pick(c, 3) == [0, 2, 3]
    assert pick(c, 4) == [0, 2, 3, 1]


def test_select_counts_and_tiers():
    n = 100
    v = pd.DataFrame({
        "kind": "video", "mature": True,
        "theme": [t for t in "ABCDE" for _ in range(n // 5)],
        "period": ["P1", "P2"] * (n // 2),
        "rel_index": [i / 10 for i in range(n)],
    })
    s = select(v, per_period=2)
    assert s.groupby("tier").size().to_dict() == {"high": 4, "low": 4, "mid": 4}
    assert s.loc[s.tier == "high", "rel_index"].min() > s.loc[s.tier == "low", "rel_index"].max()
