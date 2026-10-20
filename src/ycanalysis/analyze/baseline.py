"""主要な結論の数値を基準値として保存・照合する（回帰テスト用）

同じデータ・同じ方法論バージョンなら同じ値になることを確認する
方法論を変えて値が変わった場合は、methodology/CHANGELOG.md に影響を記録してから基準値を更新する

使い方:
    python -m ycanalysis.analyze.baseline <slug> write   # methodology/baselines/<slug>.json を作る
    python -m ycanalysis.analyze.baseline <slug> check   # 照合（差があれば終了コード1）
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from .. import METHODOLOGY_VERSION
from ..config import ROOT, load_channel
from .performance import add_performance
from .stats import compare_binary

TOL = 1e-9


def key_results(ch) -> dict:
    v = pd.read_csv(ch.processed_dir / "analysis_videos.csv")
    vid = v[v["kind"] == "video"]
    content = vid[vid["mature"] & ~vid["theme"].isin(ch.get("analysis", "exclude_themes", []))]
    out = {
        "n_videos": int(len(v)),
        "n_content": int(len(content)),
        "views_sum": int(vid["views"].sum()),
        "rel_index_median_content": float(content["rel_index"].median()),
        "rel_index_sum": float(vid["rel_index"].sum()),
    }
    for f in list(ch.settings.get("flags", {})) + ["has_question_mark", "has_number"]:
        if f in content:
            r = compare_binary(content, f)
            out[f"ratio:{f}"] = float(r["ratio"])
            out[f"p:{f}"] = float(r["p"])
    # raw から再計算した相対指数が processed と一致するか
    recomputed = add_performance(vid[["video_id", "published_at", "views", "age_days", "kind"]],
                                 window=ch.get("analysis", "neighbor_window", 10),
                                 min_age_days=ch.get("analysis", "min_age_days", 7))
    out["rel_index_recompute_maxdiff"] = float(
        (recomputed.set_index("video_id")["rel_index"] - vid.set_index("video_id")["rel_index"]).abs().max())
    return out


def path(slug: str):
    return ROOT / "methodology" / "baselines" / f"{slug}.json"


def compare(expected: dict, actual: dict) -> list[str]:
    diffs = []
    for k, e in expected.items():
        if k in ("methodology_version",):
            continue
        a = actual.get(k)
        if a is None or (isinstance(e, float) and not np.isclose(e, a, rtol=0, atol=TOL)) or \
                (not isinstance(e, float) and e != a):
            diffs.append(f"{k}: 基準 {e} / 今回 {a}")
    return diffs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("cmd", choices=["write", "check"])
    a = ap.parse_args()
    ch = load_channel(a.slug)
    res = key_results(ch)
    if a.cmd == "write":
        path(a.slug).parent.mkdir(parents=True, exist_ok=True)
        path(a.slug).write_text(json.dumps({"methodology_version": METHODOLOGY_VERSION, **res}, ensure_ascii=False, indent=2))
        print(path(a.slug))
        return
    expected = json.loads(path(a.slug).read_text())
    diffs = compare(expected, res)
    print("一致" if not diffs else "\n".join(diffs))
    raise SystemExit(1 if diffs else 0)


if __name__ == "__main__":
    main()
