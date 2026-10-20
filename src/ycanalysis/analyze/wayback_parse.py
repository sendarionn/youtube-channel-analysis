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


def parse_snapshot(html: str, expected_channel_id: str | None = None,
                   expected_handle: str | None = None) -> dict:
    out = {"subscribers": None, "video_count": None, "total_views": None, "joined": None, "videos": [],
           "subscriber_text": None, "subscriber_source": None, "identity_validated": False,
           "subscriber_precision": None}
    tv = re.search(r'viewCountText":"([\d,]+) views', html)
    if tv:
        out["total_views"] = parse_count(tv.group(1))
    jd = re.search(r'joinedDateText":\{"content":"Joined ([^"]+)"', html)
    if jd:
        out["joined"] = jd.group(1)
    vc = re.search(r'"(?:simpleText|content)":"([\d.,kK万]+\s*(?:videos|本の動画))"', html)
    if vc:
        out["video_count"] = parse_count(vc.group(1))
    m = INITIAL_DATA.search(html)
    if not m:
        if expected_channel_id:
            _scoped_html_subscriber(html, out, expected_channel_id)
        elif not expected_handle:
            _legacy_subscriber(html, out)
        return out
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return out
    _extract_target_subscribers(data, out, expected_channel_id, expected_handle)
    if out["subscribers"] is None and not expected_channel_id and not expected_handle:
        _legacy_subscriber(html, out)
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


def _scoped_html_subscriber(html: str, out: dict, channel_id: str) -> None:
    """初期データが別形式で埋め込まれたページをID近傍のフィールドから読む"""
    cid = re.escape(channel_id)
    patterns = [
        rf'subscriberCountText":"([^"]+)".{{0,3000}}?"channelId":"{cid}"',
        rf'"channelId":"{cid}".{{0,3000}}?subscriberCountText":"([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.S)
        if match:
            _set_subscribers(out, match.group(1), "channel_id_html", True)
            return


def _legacy_subscriber(html: str, out: dict) -> None:
    """識別情報を渡さない旧用途だけの互換処理"""
    head = re.search(r'"content":"([^"]{0,60}?@[^"]{0,60}?subscribers[^"]{0,5})"', html)
    subs = (re.search(r'subscriberCountText"[^}]{0,200}?(?:label|simpleText)":"([^"]+)"', html)
            or re.search(r'"(?:simpleText|content)":"([^"]{0,20}(?:subscribers|チャンネル登録者[^"]{0,10}))[^"]{0,5}"', html))
    if head:
        _set_subscribers(out, head.group(1).split("•")[-1].split("\\u2022")[-1], "unvalidated_header", False)
    elif subs:
        _set_subscribers(out, subs.group(1), "unvalidated_first_match", False)


def _subscriber_text(node: dict) -> str | None:
    value = node.get("subscriberCountText")
    text = _text(value)
    if text and re.search(r"subscribers|チャンネル登録者", text, re.I):
        return text
    return None


def _set_subscribers(out: dict, text: str, source: str, validated: bool) -> None:
    value = parse_count(text.replace("チャンネル登録者数", ""))
    if value is None:
        return
    out["subscribers"] = value
    out["subscriber_text"] = text
    out["subscriber_source"] = source
    out["identity_validated"] = validated
    out["subscriber_precision"] = "exact" if re.search(r"\d{1,3}(?:,\d{3})+", text) else "rounded_display"


def _extract_target_subscribers(data: dict, out: dict, expected_channel_id: str | None,
                                expected_handle: str | None) -> None:
    """対象IDまたはハンドルと同じ構造化領域にある登録者数だけを採用する"""
    nodes = list(_walk(data))
    if expected_channel_id:
        for node in nodes:
            if node.get("channelId") == expected_channel_id or node.get("externalId") == expected_channel_id:
                text = _subscriber_text(node)
                if text:
                    _set_subscribers(out, text, "channel_id_node", True)
                    return
    handle = expected_handle or ""
    handle = handle if handle.startswith("@") else f"@{handle}" if handle else ""
    # ページの持ち主（channelMetadataRenderer.externalId）が対象IDなら、先頭のヘッダーは対象チャンネルのもの
    # ハンドルは変更されることがある（例：海外Yパパ @neko_Ypapa → @海外Yパパ）ため、IDを優先する
    owners = {node["channelMetadataRenderer"].get("externalId") for node in nodes
              if isinstance(node.get("channelMetadataRenderer"), dict)}
    owners.discard(None)
    if expected_channel_id and owners and expected_channel_id not in owners:
        return
    owner_ok = bool(expected_channel_id and expected_channel_id in owners)
    for node in nodes:
        header = node.get("pageHeaderViewModel")
        if not isinstance(header, dict):
            continue
        serialized = json.dumps(header, ensure_ascii=False)
        if not owner_ok and handle and handle not in serialized:
            continue
        texts = [_text(x.get("text")) for x in _walk(header) if isinstance(x, dict) and "text" in x]
        text = next((x for x in texts if x and re.search(r"subscribers|チャンネル登録者", x, re.I)), None)
        if text and (owner_ok or handle):
            _set_subscribers(out, text, "page_owner_header" if owner_ok else "handle_header", True)
            return
    # 後方互換は期待する識別情報がないテスト・旧用途だけに限定する
    if expected_channel_id or expected_handle:
        return
    head = next((re.search(r'"content":"([^"]{0,60}?@[^"]{0,60}?subscribers[^"]{0,5})"',
                           json.dumps(node, ensure_ascii=False)) for node in nodes), None)
    if head:
        _set_subscribers(out, head.group(1).split("•")[-1], "unvalidated_header", False)
        return
    for node in nodes:
        text = _subscriber_text(node)
        if text:
            _set_subscribers(out, text, "unvalidated_first_match", False)
            return


def _lockup_rows(lv: dict) -> list:
    try:
        return lv["metadata"]["lockupMetadataViewModel"]["metadata"]["contentMetadataViewModel"]["metadataRows"]
    except (KeyError, TypeError):
        return []


def snapshot_time(name: str) -> datetime:
    return datetime.strptime(name[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def build(raw_wayback: Path, expected_channel_id: str | None = None,
          expected_handle: str | None = None, with_audit: bool = False):
    """観測点（有効なものだけ）と動画一覧の再生数を返す。with_audit=True なら全観測点の検証表も返す"""
    hist, views = [], []
    for f in sorted(raw_wayback.glob("*.html")):
        p = parse_snapshot(f.read_text(encoding="utf-8", errors="ignore"), expected_channel_id, expected_handle)
        t = snapshot_time(f.name)
        hist.append({"snapshot_at": t, "file": f.name, "subscribers": p["subscribers"],
                     "video_count": p["video_count"], "total_views": p["total_views"], "joined": p["joined"],
                     "subscriber_text": p["subscriber_text"], "subscriber_source": p["subscriber_source"],
                     "identity_validated": p["identity_validated"],
                     "subscriber_precision": p["subscriber_precision"]})
        for v in p["videos"]:
            views.append({"snapshot_at": t, "file": f.name, **v})
    full = pd.DataFrame(hist)
    if full.empty:
        return (full, pd.DataFrame(views), full) if with_audit else (full, pd.DataFrame(views))
    full["valid"] = full["subscribers"].notna() & full["identity_validated"].eq(True)
    h = full[full["valid"]].copy()
    # 同日の重複スナップショットは最初の1件を残す
    h["date"] = h["snapshot_at"].dt.date
    h = (h.sort_values(["date", "total_views"], na_position="last")
          .drop_duplicates("date").drop(columns="date").sort_values("snapshot_at"))
    h = flag_anomalies(h)
    if with_audit:
        return h, pd.DataFrame(views), audit_table(full, h)
    return h, pd.DataFrame(views)


def audit_table(full: pd.DataFrame, used: pd.DataFrame) -> pd.DataFrame:
    """全スナップショットの検証結果（有効・疑義あり・無効と理由）"""
    a = full.copy()
    anomaly = dict(zip(used["file"], used["anomaly"]))
    kept = set(used["file"])
    status, note = [], []
    for _, r in a.iterrows():
        if pd.isna(r["subscribers"]):
            status.append("無効")
            note.append("対象チャンネルの登録者数が見つからない（別チャンネルの値では補完しない）")
        elif not r["identity_validated"]:
            status.append("無効")
            note.append("対象チャンネルとの同一性を確認できない")
        elif r["file"] not in kept:
            status.append("重複")
            note.append("同日の別スナップショットを採用")
        elif anomaly.get(r["file"]):
            status.append("疑義あり")
            note.append("過去最大値の7割未満への急減。保存ページの古い表示の可能性があり成長分析に使わない")
        else:
            status.append("有効")
            note.append("")
    a["status"] = status
    a["note"] = note
    return a[["snapshot_at", "file", "subscriber_text", "subscribers", "subscriber_source", "identity_validated",
              "subscriber_precision", "video_count", "total_views", "status", "note"]]


def flag_anomalies(h: pd.DataFrame, ratio: float = 0.7) -> pd.DataFrame:
    """それまでの最大値の ratio 倍未満に急減した観測を異常値とする

    Wayback に保存された YouTube ページが古いキャッシュ値を表示している例があるため
    （例: ゆるコンピュータ科学ラジオ 2022-10-27 の 43.5K。前後は 131K・162K）
    """
    h = h.sort_values("snapshot_at").copy()
    h["anomaly"] = h["subscribers"] < h["subscribers"].cummax().shift(fill_value=0) * ratio
    return h
