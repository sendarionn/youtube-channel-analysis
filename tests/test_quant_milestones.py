import pandas as pd

from ycanalysis.analyze.quant import classify_milestone, milestone_candidates, milestones


def _v(titles):
    return pd.DataFrame({"pub_jst": pd.to_datetime(["2024-01-01"] * len(titles), utc=True),
                         "title": titles, "url": [str(i) for i in range(len(titles))]})


def test_milestones_require_explicit_subscriber_context():
    got = milestones(_v(["登録者10万人達成", "10万人の登録者を突破", "人口50万人都市", "商圏300万人のイオンモール"]))
    assert got["subs_claimed"].tolist() == [100000, 100000]
    assert got["url"].tolist() == ["0", "1"]


def test_achievement_phrase_and_fullwidth_digits():
    assert classify_milestone("【５万人！】深くお詫びして５万人達成テーマソング") == (50000, "achievement_phrase")
    assert classify_milestone("【祝15万人達成！】トイレ行きたい") == (150000, "achievement_phrase")
    assert classify_milestone("登録者１万人達成ありがとうございます") == (10000, "subscriber_word")


def test_other_count_nouns_are_rejected_and_recorded():
    for t in ["人口50万人都市、それでも快速の停車に消極的", "商圏300万人のイオンモールが閉店",
              "来場者10万人突破のイベント", "フォロワー5万人達成"]:
        assert classify_milestone(t)[0] is None, t
    c = milestone_candidates(_v(["1日2万人が免停の可能性", "人口7万人の町"]))
    assert not c["accepted"].any()
    assert set(c["reason"]) == {"other_count_noun"}


def test_no_milestones_returns_empty():
    assert milestones(_v(["新幹線の話", "道路の話"])).empty
