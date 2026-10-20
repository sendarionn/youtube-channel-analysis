"""報告書の主要な結論が、分析条件を変えても成り立つかを検証する（方法論の品質確認）

検証項目
1. 指標の感度：相対再生指数の近傍本数（window）を変える、別の指標（年齢・月を調整した残差）に置き換える
2. 公開からの経過日数による偏り：相対指数と経過日数の相関
3. 分類の再現性：手作業フラグと、明文化した規則による自動フラグの一致率（Cohen's κ）と、規則版での効果
4. データ品質：重複・欠損・種別の内訳

使い方:
    python -m ycanalysis.analyze.robustness <slug>
出力:
    reports/<slug>/robustness.md, processed/robustness_findings.csv
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from ..config import load_channel, record_run
from .auto_labels import RULES, apply_rules_v11
from .performance import add_performance
from .quant import md_table


def cohen_kappa(a: pd.Series, b: pd.Series) -> float:
    a, b = a.astype(int), b.astype(int)
    po = (a == b).mean()
    pe = a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean())
    return (po - pe) / (1 - pe) if pe < 1 else np.nan


def age_month_residual(df: pd.DataFrame) -> pd.Series:
    """log(再生数) を log(経過日数) と公開月で回帰した残差（月内の相対的な強さ）"""
    d = df.assign(lv=np.log(df["views"].clip(lower=1)), la=np.log(df["age_days"].clip(lower=1)))
    fit = smf.ols("lv ~ la + C(month)", data=d).fit()
    return pd.Series(fit.resid, index=d.index)


def effect(df: pd.DataFrame, col: str, metric: str, a=1, b=0) -> dict:
    x = df.loc[df[col] == a, metric].dropna()
    y = df.loc[df[col] == b, metric].dropna()
    if len(x) < 5 or len(y) < 5:
        return {"n_a": len(x), "n_b": len(y), "diff_median": np.nan, "p": np.nan}
    return {"n_a": len(x), "n_b": len(y), "diff_median": x.median() - y.median(),
            "p": stats.mannwhitneyu(x, y).pvalue}


def findings(df: pd.DataFrame, metric: str, flags: dict, tone: dict | None) -> list[dict]:
    """設定の特徴フラグ・論調・タイトル要素・尺の効果を、与えられた指標（大きいほど高実績、対数）で再計算する"""
    out = []
    for col, label in {**flags, "has_question_mark": "疑問符"}.items():
        if col in df:
            out.append({"finding": label, **effect(df, col, metric)})
    if tone and tone.get("column") in df:
        out.append({"finding": "論調 肯定 vs 否定", **effect(df, tone["column"], metric, "pos", "neg")})
    rho = stats.spearmanr(df["duration_min"], df[metric], nan_policy="omit")
    out.append({"finding": "尺（Spearman ρ）", "n_a": int(df[metric].notna().sum()), "n_b": np.nan,
                "diff_median": rho.statistic, "p": rho.pvalue})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ch = load_channel(ap.parse_args().slug)
    v = pd.read_csv(ch.processed_dir / "analysis_videos.csv", parse_dates=["published_at"])
    record_run(ch, "robustness")
    lines = ["# 頑健性チェック（自動生成）", ""]

    # 4. データ品質
    lines += ["## データ品質", "",
              f"- 動画数 {len(v)}、video_id の重複 {int(v['video_id'].duplicated().sum())}",
              f"- 種別 {v['kind'].value_counts().to_dict()}",
              f"- 欠損：再生数 {int(v['views'].isna().sum())}、高評価 {int(v['likes'].isna().sum())}、"
              f"コメント {int(v['comments'].isna().sum())}、尺 {int(v['duration_s'].isna().sum())}",
              f"- 手作業テーマの欠損 {int(v['theme'].isna().sum()) if 'theme' in v else '列なし'}", ""]

    flags = ch.settings.get("flags", {})
    tone = ch.settings.get("tone")
    base = v[(v["kind"] == "video") & v["mature"]].copy()
    if "theme" in base:
        base = base[~base["theme"].isin(ch.get("analysis", "exclude_themes", []))]

    # 1. 指標の感度
    rows = []
    vid_all = v[v["kind"] == "video"][["video_id", "published_at", "views", "age_days", "kind"]]
    for w in (5, 10, 20):
        alt = add_performance(vid_all, window=w)[["video_id", "log_rel"]].rename(columns={"log_rel": f"log_rel_w{w}"})
        base = base.drop(columns=[f"log_rel_w{w}"], errors="ignore").merge(alt, on="video_id", how="left")
        for f in findings(base, f"log_rel_w{w}", flags, tone):
            rows.append({"metric": f"相対指数 window={w}", **f})
    full = v[v["kind"] == "video"].copy()
    full["resid"] = age_month_residual(full)
    base = base.merge(full[["video_id", "resid"]], on="video_id", how="left")
    for f in findings(base, "resid", flags, tone):
        rows.append({"metric": "経過日数・公開月で調整した残差", **f})
    res = pd.DataFrame(rows)
    res.to_csv(ch.processed_dir / "robustness_findings.csv", index=False)
    piv = res.pivot_table(index="finding", columns="metric", values="p", aggfunc="first").round(4)
    eff = res.pivot_table(index="finding", columns="metric", values="diff_median", aggfunc="first").round(3)
    lines += ["## 指標を変えたときの主要な結論", "",
              "数値は中央値の差（log2 または対数残差、尺はρ）。正なら該当群が高い", "", md_table(eff.reset_index(), "{:.3f}"), "",
              "### p 値（Mann-Whitney、尺は Spearman）", "", md_table(piv.reset_index(), "{:.4f}"), ""]

    # 2. 経過日数の偏り
    rho_age = stats.spearmanr(base["age_days"], base["log_rel"])
    recent = base[base["published_at"] >= base["published_at"].max() - pd.Timedelta(days=30)]
    rho_recent = stats.spearmanr(recent["age_days"], recent["log_rel"])
    lines += ["## 公開からの経過日数による偏り", "",
              f"- 全体：相対指数と経過日数の Spearman ρ = {rho_age.statistic:.3f}（p={rho_age.pvalue:.3f}）",
              f"- 直近30日に公開された {len(recent)} 本：ρ = {rho_recent.statistic:.3f}（p={rho_recent.pvalue:.3f}）",
              "- 正の相関なら、新しい動画ほど相対指数が低く出ている（再生がまだ蓄積途中）", ""]

    # 3. 分類の再現性
    auto = apply_rules_v11(v[["video_id", "title"]])
    m = base.merge(auto, on="video_id", how="left", suffixes=("", "_rule"))
    krows = []
    for col in RULES:
        if col in m and f"{col}_rule" in m:
            k = cohen_kappa(m[col].fillna(0), m[f"{col}_rule"].fillna(0))
            e_manual = effect(m, col, "log_rel")
            e_rule = effect(m, f"{col}_rule", "log_rel")
            krows.append({"flag": col, "kappa": k, "一致率": (m[col].fillna(0) == m[f"{col}_rule"]).mean(),
                          "手作業 n": e_manual["n_a"], "手作業 差": e_manual["diff_median"], "手作業 p": e_manual["p"],
                          "規則 n": e_rule["n_a"], "規則 差": e_rule["diff_median"], "規則 p": e_rule["p"]})
    lines += ["## 手作業フラグと規則ベースのフラグ", "",
              "規則は `analyze/auto_labels.py` に明文化（タイトルのみで判定、再生数を参照しない）", ""]
    lines += [md_table(pd.DataFrame(krows), "{:.3f}"), ""] if krows else \
        ["共通フラグ（classification.md）の手作業ラベルがないため比較できない", ""]
    (ch.report_dir / "robustness.md").write_text("\n".join(lines))
    print(ch.report_dir / "robustness.md")


if __name__ == "__main__":
    main()
