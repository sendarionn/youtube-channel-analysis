"""事前登録した仮説を、代表動画の標本外で検証する（methodology/evaluation.md）

config/channels/<slug>.toml の [hypotheses] に、規則（タイトルの正規表現）と予想の向きを登録しておく
代表動画（内容分析の標本）は仮説を作った材料なので、exclude_sample=true なら検証から除く
結果は登録内容の写しと一緒に保存し、後から規則を変えた場合は別の版として扱う

使い方:
    python -m ycanalysis.analyze.hypothesis_test <slug>
出力:
    reports/<slug>/hypothesis_tests.md, processed/hypothesis_tests.csv
"""
from __future__ import annotations

import argparse
import json
import re

import numpy as np
import pandas as pd
from scipy import stats

from ..config import load_channel, record_run
from .quant import md_table
from .stats import bh_adjust


def sample_ids(ch) -> set[str]:
    for p in (ch.annotations_dir / "phase3_sample_frozen.csv", ch.processed_dir / "phase3_sample.csv"):
        if p.exists():
            return set(pd.read_csv(p)["video_id"])
    return set()


def evaluate_rule(df: pd.DataFrame, rule: str, direction: str) -> dict:
    hit = df["title"].fillna("").str.contains(rule, regex=True)
    a, b = df.loc[hit, "log_rel"].dropna(), df.loc[~hit, "log_rel"].dropna()
    out = {"n_hit": int(len(a)), "n_other": int(len(b)),
           "median_ratio": float(2 ** (a.median() - b.median())) if len(a) and len(b) else np.nan}
    if len(a) >= 5 and len(b) >= 5:
        alt = "greater" if direction == "+" else "less"
        out["p_one_sided"] = float(stats.mannwhitneyu(a, b, alternative=alt).pvalue)
    else:
        out["p_one_sided"] = np.nan
    out["direction_ok"] = bool(out["median_ratio"] > 1) if direction == "+" else bool(out["median_ratio"] < 1)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ch = load_channel(ap.parse_args().slug)
    reg = ch.settings.get("hypotheses")
    if not reg:
        print("[hypotheses] が登録されていない")
        return
    v = pd.read_csv(ch.processed_dir / "analysis_videos.csv")
    v = v[(v["kind"] == "video") & v["mature"]]
    samp = sample_ids(ch)
    groups = {"標本外（検証）": v[~v["video_id"].isin(samp)] if reg.get("exclude_sample") else v,
              "標本内（仮説の材料）": v[v["video_id"].isin(samp)]}
    rows = []
    for key, h in reg.items():
        if not isinstance(h, dict):
            continue
        for gname, g in groups.items():
            rows.append({"仮説": key, "内容": h["label"], "予想": h["direction"], "対象": gname, **evaluate_rule(g, h["rule"], h["direction"])})
    res = pd.DataFrame(rows)
    oos = res["対象"] == "標本外（検証）"
    res.loc[oos, "p_bh"] = bh_adjust(res.loc[oos, "p_one_sided"])
    res["判定"] = np.where(~oos, "（材料のため判定しない）",
                         np.where(res["direction_ok"] & (res["p_bh"] < 0.05), "支持",
                                  np.where(res["direction_ok"], "向きは一致・有意差なし", "不支持")))
    res.to_csv(ch.processed_dir / "hypothesis_tests.csv", index=False)
    lines = ["# 事前登録した仮説の標本外検証（自動生成）", "",
             f"- 登録日時 {reg.get('registered_at')}、根拠 {reg.get('basis')}",
             f"- 標本外 {len(groups['標本外（検証）'])} 本（通常動画・公開{ch.get('analysis', 'min_age_days', 7)}日以上）、"
             f"標本内 {len(groups['標本内（仮説の材料）'])} 本",
             "- 片側 Mann-Whitney（予想の向き）、p_bh は標本外の仮説間で Benjamini-Hochberg 補正",
             "- 中央値の比は相対再生指数（log2）の中央値の差を倍率に戻したもの", "",
             md_table(res[["仮説", "内容", "予想", "対象", "n_hit", "n_other", "median_ratio", "p_one_sided", "p_bh", "判定"]], "{:.3f}"),
             "", "## 登録内容", "", "```json", json.dumps({k: v for k, v in reg.items()}, ensure_ascii=False, indent=2), "```", ""]
    (ch.report_dir / "hypothesis_tests.md").write_text("\n".join(lines))
    record_run(ch, "hypothesis_test", n_out_of_sample=len(groups["標本外（検証）"]))
    print(ch.report_dir / "hypothesis_tests.md")


if __name__ == "__main__":
    main()
