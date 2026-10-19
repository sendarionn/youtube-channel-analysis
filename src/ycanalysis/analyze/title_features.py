"""タイトルの特徴量（辞書・規則ベース、チャンネル非依存）

主観を含む項目（逆説・危機感など）は語彙辞書による近似であり、
報告書では「辞書ベースの近似指標」として扱う
"""
from __future__ import annotations

import re
import unicodedata

BRACKET = re.compile(r"【([^】]*)】")
DIGIT = re.compile(r"[0-9０-９]")
NUM_WORD = re.compile(r"[0-9０-９]+|[一二三四五六七八九十百千万億兆]+(?:人|カ国|か国|ヶ国|つ|位|倍|年|円|ドル|%|％)")
KATAKANA_WORD = re.compile(r"[ァ-ヴー]{3,}")
LATIN_WORD = re.compile(r"[A-Za-zＡ-Ｚａ-ｚ]{2,}")

QUESTION_WORDS = ("なぜ", "何故", "どうして", "どう", "何が", "何を", "何で", "どこ", "誰", "いつ", "本当", "とは")
PARADOX_WORDS = ("実は", "意外", "逆に", "なのに", "のに", "じゃない", "ではない", "じゃなかった", "嘘", "誤解",
                 "勘違い", "真逆", "逆転", "勝ち組", "負け組", "マシ", "神話", "常識")
CRISIS_WORDS = ("危機", "崩壊", "終わり", "終了", "ヤバ", "やば", "危険", "破綻", "地獄", "絶望", "消滅", "滅亡",
                "衰退", "没落", "限界", "警告", "悲報", "最悪", "失敗", "暴落", "戦争", "詰み", "詰ん")
SURPRISE_WORDS = ("衝撃", "まさか", "驚", "ありえない", "あり得ない", "異常", "爆", "激", "ガチ", "最強", "史上")
CURIOSITY_WORDS = ("理由", "なぜ", "正体", "真相", "秘密", "裏", "本当", "とは", "謎", "知られざる", "仕組み", "本音")
EXPLAIN_WORDS = ("解説", "について", "とは", "まとめ", "徹底", "比較", "ランキング", "理由", "仕組み")
CELEBRATION_WORDS = ("記念", "万人", "達成", "突破")


def normalize(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def strip_brackets(title: str) -> str:
    return BRACKET.sub("", title).strip()


def sentence_form(title: str) -> str:
    """疑問形 / 断定形 / 説明形 を推定する

    - 疑問形: ？を含む、または疑問詞を含み名詞句で終わらない
    - 説明形: 「〜理由」「〜とは」「〜解説」など名詞句で終わる
    - 断定形: それ以外（言い切り）
    """
    t = normalize(title)
    body = strip_brackets(t)
    if "?" in body:
        return "question"
    if body.endswith(("理由", "とは", "解説", "まとめ", "仕組み", "話", "歴史", "正体", "真相", "実態", "現状",
                      "未来", "結末", "比較", "ランキング", "方法", "違い")):
        return "explanation"
    if any(w in body for w in QUESTION_WORDS) and body.endswith(("か", "の", "のか", "なのか")):
        return "question"
    return "assertion"


def has_any(text: str, words) -> bool:
    return any(w in text for w in words)


def title_features(title: str) -> dict:
    t = normalize(title)
    brackets = BRACKET.findall(t)
    body = strip_brackets(t)
    return {
        "title_len": len(t),
        "title_body_len": len(body),
        "has_bracket": bool(brackets),
        "bracket_text": " / ".join(brackets),
        "bracket_question": any("?" in b for b in brackets),
        "has_question_mark": "?" in t,
        "exclaim_count": t.count("!"),
        "has_number": bool(DIGIT.search(t)) or bool(NUM_WORD.search(t)),
        "has_katakana_word": bool(KATAKANA_WORD.search(t)),
        "has_latin_word": bool(LATIN_WORD.search(t)),
        "form": sentence_form(t),
        "w_paradox": has_any(t, PARADOX_WORDS),
        "w_crisis": has_any(t, CRISIS_WORDS),
        "w_surprise": has_any(t, SURPRISE_WORDS) or t.count("!") >= 2,
        "w_curiosity": has_any(t, CURIOSITY_WORDS),
        "w_explain": has_any(t, EXPLAIN_WORDS),
        "is_celebration": has_any(t, CELEBRATION_WORDS) and "登録" in t,
    }
