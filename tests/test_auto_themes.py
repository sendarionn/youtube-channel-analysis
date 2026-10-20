import pandas as pd

from ycanalysis.analyze.auto_themes import classify


def test_theme_generation_does_not_use_views():
    base = pd.DataFrame({"video_id": ["a", "b", "c", "d"],
                         "title": ["海外生活の家探し", "海外生活の食事", "料理の作り方", "料理の道具"]})
    a, model = classify(base.assign(views=[1, 2, 3, 4]))
    b, _ = classify(base.assign(views=[400, 3, 2, 1]))
    assert a["theme"].tolist() == b["theme"].tolist()
    assert model["validated"] is False
