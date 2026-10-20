import pandas as pd

from ycanalysis.annotate import cohen_kappa_nominal


def test_kappa_nominal():
    a = pd.Series(["E", "A", "G", "E"])
    assert cohen_kappa_nominal(a, a) == 1.0
    b = pd.Series(["E", "A", "G", "A"])
    k = cohen_kappa_nominal(a, b)
    assert 0 < k < 1
