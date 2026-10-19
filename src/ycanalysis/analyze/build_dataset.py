"""raw データから分析用データセット（processed/）を生成する

使い方:
    python -m ycanalysis.analyze.build_dataset <slug>
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone

import pandas as pd

from ..collect.rawstore import latest_snapshot_dir
from ..config import Channel, load_channel
from . import wayback_parse
from .performance import add_performance
from .title_features import title_features

HASHTAG = re.compile(r"#([^\s#]+)")


def video_kind(d: dict) -> str:
    if d.get("tab") == "shorts" or d.get("media_type") == "short":
        return "short"
    if d.get("was_live") or d.get("live_status") in ("was_live", "post_live", "is_live"):
        return "live"
    return "video"


def load_videos(channel: Channel) -> tuple[pd.DataFrame, dict]:
    snap = latest_snapshot_dir(channel.raw_dir, "ytdlp_videos")
    manifest = json.loads((snap / "manifest.json").read_text())
    rows = []
    for p in sorted((snap / "videos").glob("*.json")):
        d = json.loads(p.read_text())
        rows.append({
            "video_id": d["id"],
            "url": f"https://www.youtube.com/watch?v={d['id']}",
            "title": d.get("title"),
            "description": d.get("description") or "",
            "published_at": pd.to_datetime(d["timestamp"], unit="s", utc=True) if d.get("timestamp")
            else pd.to_datetime(d["upload_date"], format="%Y%m%d", utc=True),
            "duration_s": d.get("duration"),
            "kind": video_kind(d),
            "views": d.get("view_count"),
            "likes": d.get("like_count"),
            "comments": d.get("comment_count"),
            "tags": "|".join(d.get("tags") or []),
            "category": "|".join(d.get("categories") or []),
            "n_chapters": len(d.get("chapters") or []),
            "has_ja_caption": bool(d.get("subtitle_langs")) or d.get("auto_caption_has_ja", False),
            "retrieved_at": pd.to_datetime(d["retrieved_at"], utc=True),
        })
    df = pd.DataFrame(rows)
    df["age_days"] = (df["retrieved_at"] - df["published_at"]).dt.total_seconds() / 86400
    jst = df["published_at"].dt.tz_convert("Asia/Tokyo")
    df["published_jst"] = jst.dt.strftime("%Y-%m-%d %H:%M")
    df["month"] = jst.dt.strftime("%Y-%m")
    df["weekday"] = jst.dt.dayofweek
    df["hour_jst"] = jst.dt.hour
    df["duration_min"] = df["duration_s"] / 60
    df["like_rate"] = df["likes"] / df["views"]
    df["comment_rate"] = df["comments"] / df["views"]
    df["hashtags"] = df["title"].map(lambda t: "|".join(HASHTAG.findall(t or "")))
    feats = pd.DataFrame([title_features(HASHTAG.sub("", t or "").strip()) for t in df["title"]])
    df = pd.concat([df, feats], axis=1)
    df = add_performance(df)
    return df, manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ch = load_channel(ap.parse_args().slug)
    out = ch.processed_dir
    out.mkdir(parents=True, exist_ok=True)

    df, manifest = load_videos(ch)
    df.to_csv(out / "videos.csv", index=False)

    hist, snaps = wayback_parse.build(ch.raw_dir / "wayback")
    hist["source"] = "wayback"
    if (ch.raw_dir / "channel_page").exists():
        cur, _ = wayback_parse.build(ch.raw_dir / "channel_page")
        cur["source"] = "direct"
        hist = pd.concat([hist, cur]).sort_values("snapshot_at")
    hist.to_csv(out / "channel_history.csv", index=False)
    snaps.to_csv(out / "video_view_snapshots.csv", index=False)

    (out / "build_info.json").write_text(json.dumps({
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "videos_source": manifest,
        "n_videos": len(df), "kinds": df["kind"].value_counts().to_dict(),
        "n_history_points": len(hist),
    }, ensure_ascii=False, indent=2, default=str))
    print(out, len(df), df["kind"].value_counts().to_dict(), len(hist))


if __name__ == "__main__":
    main()
