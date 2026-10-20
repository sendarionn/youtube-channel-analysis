"""設定に明記したチャンネル固有規則で意味テーマを付与する"""
from __future__ import annotations

import argparse
import json
import re

import pandas as pd

from ..config import load_channel, record_run


def generate(slug: str) -> None:
    ch = load_channel(slug)
    rules = ch.settings.get("theme_rules", {})
    if not rules:
        raise SystemExit("[theme_rules] がありません")
    videos = pd.read_csv(ch.processed_dir / "videos.csv")
    rows = []
    for row in videos[["video_id", "title"]].itertuples(index=False):
        matches = [code for code, pattern in rules.items() if re.search(pattern, str(row.title))]
        rows.append({"video_id": row.video_id, "title": row.title,
                     "theme": matches[0] if matches else "other",
                     "theme_confidence": "high" if len(matches) <= 1 else "medium",
                     "theme_matches": "|".join(matches), "coding_source": "configured_semantic_rules"})
    out = pd.DataFrame(rows)
    out.to_csv(ch.annotations_dir / "labels_semantic.csv", index=False)
    counts = out["theme"].value_counts().to_dict()
    # 検証済みかどうかはここでは決めない（ycanalysis.annotate agreement の一致率で記録する）
    summary = {
        "method": "config [theme_rules] の正規表現を上から順に適用（タイトルのみ、再生数を参照しない）",
        "n_videos": len(out),
        "counts": counts,
        "ambiguous": int((out["theme_confidence"] == "medium").sum()),
        "unclassified": int((out["theme"] == "other").sum()),
    }
    (ch.annotations_dir / "theme_rules_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    record_run(ch, "configured_themes", **summary)
    print(ch.annotations_dir / "labels_semantic.csv")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    generate(ap.parse_args().slug)


if __name__ == "__main__":
    main()
