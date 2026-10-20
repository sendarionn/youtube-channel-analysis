"""明文化した規則によるタイトルの自動フラグ（方法論 v1.1）

手作業コーディングの再現性を確認するための比較基準として使う
規則はタイトル文字列だけを見て判定し、再生実績は参照しない
語彙は日本語チャンネル向け。対象の国・ジャンルが違う場合は config の [auto_labels] で上書きする
"""
from __future__ import annotations

import re

import pandas as pd

RULES: dict[str, str] = {
    # 視聴者の国（日本）との結びつき
    "japan_angle": r"日本|日銀|邦人|国産|和食|東京|大阪|円安|円高|円キャリー|日経|トヨタ|ホンダ|ソニー|高市|自民",
    # 国同士の比較・順位・競争形式（v1.0 の規則。多国間ランキング型のみ）
    "intl_compare": r"ランキング|コンテスト|レース|大会|対決|[0-9０-９一二三四五六七八九十]+位|世界一|"
                    r"一番.{0,8}国|国.{0,6}(?:比較|vs|VS|対)|(?:比較|vs|VS).{0,10}国|どの国|各国|カ国|か国",
    # 通説と逆の結論
    "counterintuitive": r"実は|じゃない|ではない|じゃなかった|だから何|マシ|意外|勘違い|誤解|嘘|"
                        r"関係ない|無くならない|ならない理由|知らない",
    # 危機・不安
    "anxiety": r"危機|崩壊|ヤバ|やば|地獄|破綻|絶望|消滅|終わ|悲報|暴落|警告|詰|末路",
    # 直近の出来事
    "timely": r"速報|上場|逮捕|発表|決定|解禁|達成|判明|開始|炎上|演説|会見|[0-9０-９]+月",
}


def apply_rules(df: pd.DataFrame, rules: dict[str, str] | None = None) -> pd.DataFrame:
    """df の title 列に規則を適用し、<flag>_rule 列（0/1）を返す"""
    rules = rules or RULES
    out = df[["video_id"]].copy()
    for name, pat in rules.items():
        rx = re.compile(pat)
        out[f"{name}_rule"] = df["title"].fillna("").map(lambda t: int(bool(rx.search(t))))
    return out


# v1.1：国際比較を2種類に分ける
COUNTRIES = (r"日本|中国|韓国|台湾|アメリカ|米国|米中|日米|日中|ロシア|ウクライナ|ニュージーランド|ニュージー|NZ|"
             r"オーストラリア|豪州|豪中|シンガポール|タイ|インド|インドネシア|ベトナム|イラン|トルコ|ドイツ|フランス|"
             r"イギリス|英国|欧州|EU|西洋|先進国|諸外国|他国|海外|世界|トヨタ|テスラ")
COMPARE_CUE = r"より|対|vs|VS|比較|比べ|違|追いつ|抜|倍|にはあって|には無く|にはなく|勝|負|どちら|両想い|片思い"


def two_country_compare(title: str) -> int:
    """2つ以上の国（または国を代表する企業）に言及し、比較の語を含む"""
    names = set(re.findall(COUNTRIES, title))
    return int(len(names) >= 2 and bool(re.search(COMPARE_CUE, title)))


def apply_rules_v11(df: pd.DataFrame) -> pd.DataFrame:
    out = apply_rules(df)
    out["intl_ranking_rule"] = out["intl_compare_rule"]
    out["intl_pair_rule"] = df["title"].fillna("").map(two_country_compare)
    out["intl_compare_rule"] = (out["intl_ranking_rule"] | out["intl_pair_rule"]).astype(int)
    return out
