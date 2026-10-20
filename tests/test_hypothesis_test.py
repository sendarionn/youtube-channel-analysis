import numpy as np
import pandas as pd

from ycanalysis.analyze.hypothesis_test import evaluate_rule


def test_direction_and_one_sided_p():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"title": ["開通した道"] * 20 + ["普通の話"] * 40,
                       "log_rel": np.r_[rng.normal(1, 0.3, 20), rng.normal(0, 0.3, 40)]})
    r = evaluate_rule(df, "開通", "+")
    assert r["direction_ok"] and r["p_one_sided"] < 0.01 and r["n_hit"] == 20
    r = evaluate_rule(df, "開通", "-")
    assert not r["direction_ok"] and r["p_one_sided"] > 0.9
