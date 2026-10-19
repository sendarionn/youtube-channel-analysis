from ycanalysis.analyze.title_features import sentence_form, strip_brackets, title_features


def test_brackets_and_question():
    f = title_features("【なぜ？】少子化の先頭だった日本が韓国、台湾にごぼう抜きされた理由")
    assert f["has_bracket"]
    assert f["bracket_question"]
    assert f["has_question_mark"]
    assert f["w_curiosity"]


def test_strip_brackets():
    assert strip_brackets("【速報】AIが来た") == "AIが来た"


def test_sentence_form():
    assert sentence_form("日本はなぜ貧しくなったのか") == "question"
    assert sentence_form("円安が止まらない？") == "question"
    assert sentence_form("【解説】日本が韓国に抜かれた理由") == "explanation"
    assert sentence_form("中国経済はもう終わった") == "assertion"


def test_number_and_words():
    f = title_features("世界3位の経済大国が崩壊する")
    assert f["has_number"]
    assert f["w_crisis"]
    assert not title_features("経済の話")["has_number"]


def test_celebration():
    assert title_features("【祝16万人登録記念】歌を作りました")["is_celebration"]
