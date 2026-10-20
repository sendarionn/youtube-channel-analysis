"""タイトルからチャンネル固有の暫定テーマを自動生成する

再生数を参照せず、複数タイトルに現れる文字列だけで分類する
結果は手作業ラベルと区別して labels_auto.csv に保存する
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter

import pandas as pd

from ..config import load_channel, record_run

NOISE = re.compile(r"[\s\d０-９【】\[\]（）()!！?？、。・…\-_]+")
STOP = re.compile(
    r"している|されている|なっている|について|として|っている|れている|されてい|なってい|"
    r"わかりやすく|どうなる|だったら|なのに|だけど|しかし|なぜ|理由|解説|"
    r"ある|いる|する|した|して|です|ます|ない|った|でも|のに|なの|しか|たら|って|これ"
)
PARTICLES = tuple("のにはをがでとへもやか")


def candidates(titles: list[str], max_themes: int = 6) -> list[str]:
    docs: list[set[str]] = []
    contexts: dict[str, tuple[set[str], set[str]]] = {}
    for title in titles:
        clean = NOISE.sub("", str(title))
        found = set()
        for n in range(2, 9):
            for i in range(max(0, len(clean) - n + 1)):
                phrase = clean[i:i + n]
                found.add(phrase)
                left, right = contexts.setdefault(phrase, (set(), set()))
                left.add(clean[i - 1:i] or "^")
                right.add(clean[i + n:i + n + 1] or "$")
        docs.append(found)
    counts = Counter(x for doc in docs for x in doc)
    minimum = 2 if len(titles) < 30 else max(3, round(len(titles) * .04))
    pool = [x for x, n in counts.items()
            if minimum <= n <= max(minimum, len(titles) * .6)
            and not STOP.search(x) and not x.startswith(PARTICLES) and not x.endswith(PARTICLES)
            and len(contexts[x][0]) >= 2 and len(contexts[x][1]) >= 2]
    pool.sort(key=lambda x: (counts[x] * len(x) * len(contexts[x][0]) * len(contexts[x][1]),
                             counts[x], len(x), x), reverse=True)
    chosen: list[str] = []
    for phrase in pool:
        if any(phrase in old or old in phrase for old in chosen):
            continue
        chosen.append(phrase)
        if len(chosen) == max_themes:
            break
    return chosen


def classify(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    texts = df["title"].fillna("").astype(str).tolist()
    phrases = candidates(texts)
    codes = {p: "auto_" + hashlib.sha1(p.encode()).hexdigest()[:8] for p in phrases}
    rows = []
    for r, text in zip(df[["video_id", "title"]].itertuples(index=False), texts):
        matches = [p for p in phrases if p in text]
        best = max(matches, key=lambda p: (len(p), p)) if matches else None
        rows.append({"video_id": r.video_id, "title": r.title,
                     "theme": codes[best] if best else "auto_other",
                     "theme_confidence": "medium" if best and len(matches) == 1 else "low"})
    themes = {code: f"「{phrase}」を含む" for phrase, code in codes.items()}
    themes["auto_other"] = "その他・未確定"
    return pd.DataFrame(rows), {"themes": themes, "phrases": phrases,
                                "method": "title_repeated_substrings_with_grammar_filter", "validated": False}


def generate(slug: str) -> None:
    ch = load_channel(slug)
    manual = ch.annotations_dir / "labels_manual.csv"
    if manual.exists():
        print("手作業ラベルがあるため自動テーマを作成しない")
        record_run(ch, "auto_themes", status="skipped_manual_labels")
        return
    df = pd.read_csv(ch.processed_dir / "videos.csv")
    labels, model = classify(df)
    ch.annotations_dir.mkdir(parents=True, exist_ok=True)
    labels.to_csv(ch.annotations_dir / "labels_auto.csv", index=False)
    (ch.annotations_dir / "theme_model.json").write_text(json.dumps(model, ensure_ascii=False, indent=2))
    codebook = "\n".join([f"# {ch.name} 自動テーマ分類", "",
        "- タイトルを使用し、再生数は参照していない",
        "- 概要欄は定型の出典表記が多数を占めたため分類入力から除外",
        "- 複数動画で反復する文字列による暫定分類",
        "- 人手による妥当性確認と一致率検証は未実施",
        "- `theme_confidence` が `low` の判定は結論の単独根拠にしない", "",
        "## 分類基準", ""] + [f"- `{k}` {v}" for k, v in model["themes"].items()]) + "\n"
    (ch.annotations_dir / "AUTO_THEME_CODEBOOK.md").write_text(codebook)
    record_run(ch, "auto_themes", n_videos=len(labels), n_themes=len(model["themes"]), validated=False)
    print(ch.annotations_dir / "labels_auto.csv")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    generate(ap.parse_args().slug)


if __name__ == "__main__":
    main()
