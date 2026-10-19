"""Wayback スナップショット（YouTube チャンネルページ HTML）から過去の数値を抽出する

出力:
- processed/channel_history.csv: snapshot_at, subscribers, video_count（ページ表示値、丸めあり）
- processed/video_view_snapshots.csv: snapshot_at, video_id, views（動画一覧に表示された丸め値）
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

INITIAL_DATA = re.compile(r"(?:var ytInitialData|window\[\"ytInitialData\"\])\s*=\s*(\{.*?\});\s*</script>", re.S)
COUNT = re.compile(r"([\d.,]+)\s*(thousand|million|[kKmM万千]?)")


def parse_count(text: str | None) -> float | None:
    """'33.2k subscribers' '1.3万人' '947 views' '1,234 views' を数値にする"""
    if not text:
        return None
    t = text.replace(",", "")
    if re.search(r"no views|視聴なし", t, re.I):
        return 0.0
    m = COUNT.search(t)
    if not m:
        return None
    n = float(m.group(1))
    mult = {"k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6, "万": 1e4, "千": 1e3, "thousand": 1e3, "million": 1e6,
            "": 1}[m.group(2)]
    return n * mult


def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def _text(o) -> str | None:
    if not isinstance(o, dict):
        return o if isinstance(o, str) else None
    if "simpleText" in o:
        return o["simpleText"]
    if "runs" in o:
        return "".join(r.get("text", "") for r in o["runs"])
    if "content" in o:
        return o["content"]
    return None


def parse_snapshot(html: str) -> dict:
    out = {"subscribers": None, "video_count": None, "total_views": None, "joined": None, "videos": []}
    tv = re.search(r'viewCountText":"([\d,]+) views', html)
    if tv:
        out["total_views"] = parse_count(tv.group(1))
    jd = re.search(r'joinedDateText":\{"content":"Joined ([^"]+)"', html)
    if jd:
        out["joined"] = jd.group(1)
    # 新レイアウトはヘッダーの「@handle • 1.07M subscribers」、旧レイアウトは subscriberCountText
    # （おすすめチャンネル欄にも subscriberCountText があるため、ヘッダー表記を優先する）
    head = re.search(r'"content":"([^"]{0,60}?@[^"]{0,60}?subscribers[^"]{0,5})"', html)
    subs = (re.search(r'subscriberCountText"[^}]{0,200}?(?:label|simpleText)":"([^"]+)"', html)
            or re.search(r'"(?:simpleText|content)":"([^"]{0,20}(?:subscribers|チャンネル登録者[^"]{0,10}))[^"]{0,5}"', html))
    if head:
        out["subscribers"] = parse_count(head.group(1).split("•")[-1].split("\\u2022")[-1])
    elif subs:
        out["subscribers"] = parse_count(subs.group(1).replace("チャンネル登録者数", ""))
    vc = re.search(r'"(?:simpleText|content)":"([\d.,kK万]+\s*(?:videos|本の動画))"', html)
    if vc:
        out["video_count"] = parse_count(vc.group(1))
    m = INITIAL_DATA.search(html)
    if not m:
        return out
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return out
    seen = set()
    for node in _walk(data):
        vr = node.get("videoRenderer") or node.get("gridVideoRenderer")
        if isinstance(vr, dict) and vr.get("videoId") and vr["videoId"] not in seen:
            views = parse_count(_text(vr.get("viewCountText")))
            if views is not None:
                seen.add(vr["videoId"])
                out["videos"].append({"video_id": vr["videoId"], "views": views,
                                      "published_text": _text(vr.get("publishedTimeText"))})
        # 2026年以降の新レイアウト（lockupViewModel）
        lv = node.get("lockupViewModel")
        if isinstance(lv, dict) and lv.get("contentId") and lv["contentId"] not in seen:
            parts = [_text(p.get("text")) for row in _lockup_rows(lv) for p in row.get("metadataParts", [])]
            view_txt = next((p for p in parts if p and re.search(r"views|回視聴", p)), None)
            if view_txt:
                seen.add(lv["contentId"])
                out["videos"].append({"video_id": lv["contentId"], "views": parse_count(view_txt),
                                      "published_text": next((p for p in parts if p and p != view_txt), None)})
    return out


def _lockup_rows(lv: dict) -> list:
    try:
        return lv["metadata"]["lockupMetadataViewModel"]["metadata"]["contentMetadataViewModel"]["metadataRows"]
    except (KeyError, TypeError):
        return []


def snapshot_time(name: str) -> datetime:
    return datetime.strptime(name[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def build(raw_wayback: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    hist, views = [], []
    for f in sorted(raw_wayback.glob("*.html")):
        p = parse_snapshot(f.read_text(encoding="utf-8", errors="ignore"))
        t = snapshot_time(f.name)
        hist.append({"snapshot_at": t, "file": f.name, "subscribers": p["subscribers"],
                     "video_count": p["video_count"], "total_views": p["total_views"], "joined": p["joined"]})
        for v in p["videos"]:
            views.append({"snapshot_at": t, "file": f.name, **v})
    h = pd.DataFrame(hist).dropna(subset=["subscribers"])
    # 同日の重複スナップショットは最初の1件を残す
    h["date"] = h["snapshot_at"].dt.date
    h = (h.sort_values(["date", "total_views"], na_position="last")
          .drop_duplicates("date").drop(columns="date").sort_values("snapshot_at"))
    h = flag_anomalies(h)
    return h, pd.DataFrame(views)


def flag_anomalies(h: pd.DataFrame, ratio: float = 0.7) -> pd.DataFrame:
    """それまでの最大値の ratio 倍未満に急減した観測を異常値とする

    Wayback に保存された YouTube ページが古いキャッシュ値を表示している例があるため
    （例: ゆるコンピュータ科学ラジオ 2022-10-27 の 43.5K。前後は 131K・162K）
    """
    h = h.sort_values("snapshot_at").copy()
    h["anomaly"] = h["subscribers"] < h["subscribers"].cummax().shift(fill_value=0) * ratio
    return h
