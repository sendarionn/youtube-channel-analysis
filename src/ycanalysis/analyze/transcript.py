"""字幕（json3）の解析

自動字幕は誤認識を含むため、話速・語彙の指標は近似値として扱う
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CTA_PATTERNS = {
    "subscribe": r"チャンネル登録|登録して|登録お願い|登録よろしく",
    "like": r"高評価|グッドボタン|いいね",
    "comment": r"コメント",
    "next_video": r"次の動画|関連動画|こちらの動画|概要欄|前回の動画|別の動画",
}
QUESTION = re.compile(r"(なぜ|なんで|どうして|でしょうか|ですか|んですか|のか|かな)[?？]?$")


def load_json3(path: Path) -> list[dict]:
    """[{start, end, text}] を返す（秒）"""
    d = json.loads(path.read_text())
    segs = []
    for ev in d.get("events", []):
        if "segs" not in ev:
            continue
        text = "".join(s.get("utf8", "") for s in ev["segs"]).replace("\n", " ").strip()
        if not text:
            continue
        start = ev.get("tStartMs", 0) / 1000
        segs.append({"start": start, "end": start + ev.get("dDurationMs", 0) / 1000, "text": text})
    return segs


def text_between(segs: list[dict], t0: float, t1: float) -> str:
    return "".join(s["text"] for s in segs if t0 <= s["start"] < t1)


def char_count(text: str) -> int:
    return len(re.sub(r"\s|\[.*?\]", "", text))


def speech_stats(segs: list[dict], duration: float) -> dict:
    full = "".join(s["text"] for s in segs)
    n = char_count(full)
    speaking = sum(s["end"] - s["start"] for s in segs)
    katakana = re.findall(r"[ァ-ヴー]{3,}", full)
    latin = re.findall(r"[A-Za-z]{2,}", full)
    return {
        "chars": n,
        "chars_per_min": n / (duration / 60) if duration else None,
        "katakana_words_per_1k": len(katakana) / n * 1000 if n else None,
        "latin_words_per_1k": len(latin) / n * 1000 if n else None,
        "caption_coverage": min(1.0, speaking / duration) if duration else None,
        **{f"cta_{k}": len(re.findall(p, full)) for k, p in CTA_PATTERNS.items()},
        "cta_in_last_60s": bool(re.search("|".join(CTA_PATTERNS.values()),
                                          text_between(segs, duration - 60, duration + 1))),
        "cta_in_first_60s": bool(re.search("|".join(CTA_PATTERNS.values()), text_between(segs, 0, 60))),
    }


def opening_text(segs: list[dict], seconds: float = 60) -> str:
    return text_between(segs, 0, seconds)


def minute_blocks(segs: list[dict], duration: float, step: float = 60) -> list[tuple[float, str]]:
    out, t = [], 0.0
    while t < duration:
        out.append((t, text_between(segs, t, t + step)))
        t += step
    return out


def first_time(segs: list[dict], pattern: str) -> float | None:
    """pattern に最初に一致した位置を含む字幕の開始秒

    自動字幕は細かく分割されるため、連結したテキスト上で検索し、一致位置から字幕を逆引きする
    """
    starts, pos = [], 0
    for s in segs:
        starts.append(pos)
        pos += len(s["text"])
    m = re.search(pattern, "".join(s["text"] for s in segs))
    if not m:
        return None
    i = max(k for k, p in enumerate(starts) if p <= m.start())
    return segs[i]["start"]
