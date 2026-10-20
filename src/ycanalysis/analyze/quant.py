"""Phase 2: 定量分析（集計表とグラフを生成する）

入力:
- processed/videos.csv, channel_history.csv, video_view_snapshots.csv（build_dataset で生成）
- annotations/labels_manual.csv（手作業のテーマ・特徴コーディング。任意。ない場合はテーマ・特徴の節を省略）
- config/channels/<slug>.toml の [analysis]・[themes]・[flags]・[tone]・[series]
出力:
- reports/<slug>/charts/*.png
- reports/<slug>/phase2_tables.md（自動生成の集計表）
- processed/analysis_videos.csv（分析に使った最終テーブル）

使い方:
    python -m ycanalysis.analyze.quant <slug>
"""
from __future__ import annotations

import argparse
import re

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from ..config import load_channel, record_run
from ..visualize import style
from ..visualize.style import MUTED, SERIES, TEXT_2, plt, save
from .stats import bh_adjust, compare_binary, compare_groups

UNCLASSIFIED = "未分類"
TITLE_FEATURES = {"has_bracket": "【】隅付き括弧", "has_question_mark": "疑問符", "has_number": "数字",
                  "has_katakana_word": "カタカナ語(固有名詞の近似)", "has_latin_word": "英字語",
                  "w_paradox": "逆説語彙", "w_crisis": "危機語彙", "w_surprise": "驚き語彙",
                  "w_curiosity": "好奇心語彙", "w_explain": "説明語彙"}
DUR_BINS = [0, 5, 10, 13, 16, 20, 200]
DUR_LABELS = ["〜5分", "5〜10分", "10〜13分", "13〜16分", "16〜20分", "20分〜"]
MILESTONE = re.compile(r"(\d+)万(?:人)?")
MILESTONE_NC = r"\d+万"


def has_labels(ch) -> bool:
    return label_path(ch) is not None


def label_path(ch):
    for name in ("labels_manual.csv", "labels_auto.csv"):
        path = ch.annotations_dir / name
        if path.exists():
            return path
    return None


def load(ch):
    """*_jst 列は設定 timezone の現地時刻（既定 Asia/Tokyo）。列名は v1.0 との互換のため維持"""
    v = pd.read_csv(ch.processed_dir / "videos.csv", parse_dates=["published_at", "retrieved_at"])
    if has_labels(ch):
        lab = pd.read_csv(label_path(ch)).drop(columns="title", errors="ignore")
        v = v.merge(lab, on="video_id", how="left")
    else:
        v["theme"] = np.nan
    themes = ch.settings.get("themes", {})
    model = ch.annotations_dir / "theme_model.json"
    if not themes and model.exists():
        import json
        themes = json.loads(model.read_text()).get("themes", {})
    v["theme_name"] = v["theme"].map(themes).fillna(UNCLASSIFIED)
    v["pub_jst"] = v["published_at"].dt.tz_convert(ch.timezone)
    v["date_jst"] = v["pub_jst"].dt.date
    v["dur_bin"] = pd.cut(v["duration_min"], DUR_BINS, labels=DUR_LABELS, right=False)
    a, b = slot_hours(ch)
    v["morning_slot"] = v["hour_jst"].between(a, b)
    h = pd.read_csv(ch.processed_dir / "channel_history.csv", parse_dates=["snapshot_at"])
    s = pd.read_csv(ch.processed_dir / "video_view_snapshots.csv", parse_dates=["snapshot_at"])
    return v, h, s


def milestones(v: pd.DataFrame) -> pd.DataFrame:
    """登録者数の節目を告知した動画（自己申告。公開日は到達日以降）"""
    m = v[v["title"].str.contains("登録者|達成|万人", regex=True) & v["title"].str.contains(MILESTONE_NC)].copy()
    m["subs_claimed"] = m["title"].map(lambda t: int(MILESTONE.search(t).group(1)) * 10000)
    return m[["pub_jst", "subs_claimed", "title", "url"]]


def slot_hours(ch) -> tuple[int, int]:
    s = ch.get("analysis", "posting_slot", [6, 7])
    return s[0], s[-1]


def slot_label(ch) -> str:
    a, b = slot_hours(ch)
    return f"{'朝' if b < 12 else ''}{a}〜{b}時台"


def tz_label(ch) -> str:
    return "JST" if ch.timezone == "Asia/Tokyo" else ch.timezone


def fmt_subs(n: int) -> str:
    return f"{n // 10000}万" if n % 10000 == 0 else f"{n:,}"


def assign_period(v: pd.DataFrame, ms: pd.DataFrame, marks: list[int]) -> pd.Series:
    """登録者の節目告知（例：1万・5万・10万）で期間を区切る

    節目告知が1つも見つからない場合は、公開順に本数で4等分する
    """
    found = [(n, ms.loc[ms["subs_claimed"] == n, "pub_jst"].min()) for n in marks
             if len(ms) and (ms["subs_claimed"] == n).any()]
    if not found:
        # 通常動画の公開日の四分位で区切り、Shorts・ライブも同じ日付で割り当てる
        base = v.loc[v["kind"] == "video", "published_at"] if "kind" in v else v["published_at"]
        cuts = base.quantile([0.25, 0.5, 0.75]).tolist()
        idx = sum((v["published_at"] >= c).astype(int) for c in cuts)
        return idx.map(lambda i: f"P{i + 1} 公開日{i + 1}/4")
    labels = [f"P1 〜{fmt_subs(found[0][0])}"]
    labels += [f"P{i + 2} {fmt_subs(found[i][0])}〜{fmt_subs(found[i + 1][0])}" for i in range(len(found) - 1)]
    out = pd.Series(f"P{len(found) + 1} {fmt_subs(found[-1][0])}〜", index=v.index)
    for (n, t), label in reversed(list(zip(found, labels))):
        out[v["pub_jst"] < t] = label
    return out


def md_table(df: pd.DataFrame, floatfmt: str = "{:.2f}") -> str:
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_float_dtype(df[c]):
            df[c] = df[c].map(lambda x: "" if pd.isna(x) else floatfmt.format(x))
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(x) for x in r.values) + " |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ch = load_channel(ap.parse_args().slug)
    style.setup()
    charts = ch.report_dir / "charts"
    v, h, snaps = load(ch)
    ms = milestones(v)
    v["period"] = assign_period(v, ms, ch.get("analysis", "period_milestones", []))
    themes = ch.settings.get("themes", {})
    flags = {k: lab for k, lab in ch.settings.get("flags", {}).items() if k in v}
    exclude = ch.get("analysis", "exclude_themes", [])
    min_age = ch.get("analysis", "min_age_days", 7)
    exclude_label = ch.get("analysis", "exclude_label", "・".join(themes.get(t, t) for t in exclude))
    labeled = has_labels(ch)
    out: list[str] = ["# Phase 2 集計表（自動生成）", "",
                      f"生成元: processed/videos.csv（取得 {v['retrieved_at'].min():%Y-%m-%d %H:%M} UTC）", ""]

    vid = v[(v["kind"] == "video")].copy()
    mature = vid[vid["mature"]].copy()
    content = mature[~mature["theme"].isin(exclude)]

    # ---- 1. 成長過程 ----
    out += ["## 1. 成長過程", "", "### 登録者数・総再生数の観測値", ""]
    hh = h[["snapshot_at", "subscribers", "video_count", "total_views", "source"]].copy()
    hh["snapshot_at"] = hh["snapshot_at"].dt.strftime("%Y-%m-%d")
    hh["subs_per_day"] = h["subscribers"].diff() / h["snapshot_at"].diff().dt.total_seconds() * 86400
    out += [md_table(hh, "{:,.0f}"), ""]
    out += ["### 登録者数の節目告知（タイトルの自己申告）", "",
            md_table(ms.assign(pub_jst=ms["pub_jst"].dt.strftime("%Y-%m-%d"))[["pub_jst", "subs_claimed", "title"]]), ""]

    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.plot(h["snapshot_at"].dt.tz_convert(ch.timezone), h["subscribers"], marker="o", ms=5,
            color=SERIES[0], label="チャンネルページ表示値（Wayback・直接取得）")
    ax.scatter(ms["pub_jst"], ms["subs_claimed"], marker="D", s=40, color=SERIES[1], zorder=3,
               edgecolor="white", linewidth=1.5, label="節目告知動画の公開日")
    for _, r in ms.iterrows():
        ax.annotate(f"{r['subs_claimed'] // 10000}万", (r["pub_jst"], r["subs_claimed"]), xytext=(-6, 8),
                    textcoords="offset points", fontsize=8, color=TEXT_2, ha="right")
    ax.axvline(v["pub_jst"].min(), color=MUTED, lw=1, ls="--")
    ax.annotate("初投稿", (v["pub_jst"].min(), 0), xytext=(4, 6), textcoords="offset points", fontsize=8, color=TEXT_2)
    ax.set_title("登録者数の推移")
    ax.yaxis.set_major_formatter(lambda x, _: f"{x / 10000:.0f}万")
    ax.legend(frameon=False, loc="upper left")
    save(fig, charts / "01_subscribers.png")

    monthly = vid.groupby("month").agg(本数=("video_id", "size"), 中央値再生=("views", "median"),
                                       平均尺分=("duration_min", "mean"), 合計再生=("views", "sum"))
    out += ["### 月別の投稿本数と再生数", "", md_table(monthly.reset_index(), "{:,.1f}"), ""]
    fig, axes = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True)
    axes[0].bar(monthly.index, monthly["本数"], color=SERIES[0], width=0.6)
    axes[0].set_title("月別の投稿本数（通常動画）")
    axes[1].bar(monthly.index, monthly["中央値再生"], color=SERIES[0], width=0.6)
    axes[1].set_title("月別の再生数中央値（累計・取得時点）")
    axes[1].yaxis.set_major_formatter(lambda x, _: f"{x / 10000:.0f}万")
    save(fig, charts / "02_monthly.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.scatter(vid["pub_jst"], vid["views"], s=14, color=SERIES[0], alpha=0.6, edgecolor="none")
    top = vid.nlargest(8, "rel_index")
    ax.scatter(top["pub_jst"], top["views"], s=30, color=SERIES[1], edgecolor="white", linewidth=1.5, zorder=3)
    for _, r in top.iterrows():
        ax.annotate(re.sub(r"【.*?】|\(.*?\)|（.*?）", "", r["title"])[:14], (r["pub_jst"], r["views"]),
                    xytext=(4, 2), textcoords="offset points", fontsize=7.5, color=TEXT_2)
    med = vid.set_index("pub_jst")["views"].rolling("21D").median()
    ax.plot(med.index, med.values, color=TEXT_2, lw=1.2, label="21日移動中央値")
    ax.set_yscale("log")
    style.compact_dates(ax, vid["pub_jst"])
    ax.set_title("動画ごとの再生数（対数軸）と相対再生指数の上位8本")
    ax.legend(frameon=False, loc="lower right")
    save(fig, charts / "03_views_timeline.png")

    out += ["### 相対再生指数の上位15本（通常動画）", "",
            md_table(vid.nlargest(15, "rel_index")[["published_jst", "theme", "views", "rel_index", "duration_min", "title"]]), ""]
    out += [f"### 相対再生指数の下位15本（通常動画・公開{min_age}日以上）", "",
            md_table(mature.nsmallest(15, "rel_index")[["published_jst", "theme", "views", "rel_index", "duration_min", "title"]]), ""]

    # 登録者急増区間と、その区間に公開された上位動画
    out += ["### 登録者の観測区間ごとの増加と、区間内の上位動画", ""]
    hs = h.sort_values("snapshot_at").reset_index(drop=True)
    rows = []
    for i in range(1, len(hs)):
        t0, t1 = hs.loc[i - 1, "snapshot_at"], hs.loc[i, "snapshot_at"]
        inside = vid[(vid["published_at"] >= t0) & (vid["published_at"] < t1)]
        best = inside.nlargest(2, "views")
        rows.append({"区間": f"{t0:%m/%d}→{t1:%m/%d}", "日数": round((t1 - t0).total_seconds() / 86400, 1),
                     "登録者増": hs.loc[i, "subscribers"] - hs.loc[i - 1, "subscribers"],
                     "1日あたり": (hs.loc[i, "subscribers"] - hs.loc[i - 1, "subscribers"]) / max((t1 - t0).total_seconds() / 86400, 0.1),
                     "投稿数": len(inside),
                     "区間内の再生上位": " / ".join(f"{t[:22]}({x / 10000:.0f}万)" for t, x in zip(best["title"], best["views"]))})
    out += [md_table(pd.DataFrame(rows), "{:,.0f}"), ""]

    # ---- 2. 期間 ----
    per = vid.groupby("period").agg(本数=("video_id", "size"), 期間開始=("published_jst", "min"),
                                    尺中央値=("duration_min", "median"), 再生中央値=("views", "median"),
                                    **{f"{slot_label(ch).replace('〜', '_').replace('時台', '時')}の比率": ("morning_slot", "mean")})
    th_share = pd.crosstab(vid["period"], vid["theme_name"], normalize="index").round(2)
    by_milestone = v["period"].str.contains("万|〜").any()
    title2 = "## 2. 期間（登録者の節目で区切る）" if by_milestone else "## 2. 期間（節目告知がないため通常動画の公開日で4等分）"
    out += [title2, "", md_table(per.reset_index()), "", "### 期間別のテーマ構成比", "",
            md_table(th_share.reset_index()), ""]

    # ---- 3. テーマ ----
    if not labeled:
        out += ["## 3. テーマ", "", "annotations/labels_manual.csv がないため省略（methodology/classification.md の手順で作成する）", ""]
    else:
        theme_section(ch, out, mature, content, charts)

    # ---- 4. 特徴フラグ・タイトル要素 ----
    feature_section(ch, out, content, charts, flags, exclude_label, min_age)
    if labeled and ch.settings.get("tone"):
        tone_section(ch, out, content, charts)
    title_form_section(out, content)
    regression_section(ch, out, content, flags, labeled)

    # ---- 5. 動画尺 ----
    duration_section(ch, out, vid, content, charts)

    # ---- 6. 投稿戦略 ----
    posting_section(ch, out, vid, content, charts)

    # ---- 7. エンゲージメント ----
    eng = content[["like_rate", "comment_rate", "rel_index"]].corr(method="spearman").round(3)
    out += ["## 7. 高評価率・コメント率と相対再生指数（Spearman）", "", md_table(eng.reset_index()), "",
            f"高評価率の中央値 {content['like_rate'].median():.4f}、コメント率の中央値 {content['comment_rate'].median():.5f}", ""]

    # ---- 8. Wayback の再生数スナップショット ----
    accumulation_section(ch, out, vid, snaps)

    v.to_csv(ch.processed_dir / "analysis_videos.csv", index=False)
    (ch.report_dir / "phase2_tables.md").write_text("\n".join(out))
    record_run(ch, "quant", labeled=labeled, n_videos=len(v))
    print(ch.report_dir / "phase2_tables.md")


def theme_section(ch, out, mature, content, charts):
    g = compare_groups(mature, "theme_name")
    out += [f"## 3. テーマ別の相対再生指数（通常動画・公開{ch.get('analysis', 'min_age_days', 7)}日以上）", "",
            f"Kruskal-Wallis p = {g.attrs['kruskal_p']:.4f}", "", md_table(g.reset_index()), ""]
    order = g.index.tolist()[::-1]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for i, t in enumerate(order):
        y = mature.loc[mature["theme_name"] == t, "rel_index"]
        jitter = (np.random.default_rng(0).random(len(y)) - 0.5) * 0.35
        ax.scatter(y, i + jitter, s=10, color=SERIES[0], alpha=0.45, edgecolor="none")
        ax.plot([y.median()] * 2, [i - 0.3, i + 0.3], color=SERIES[1], lw=2.5)
        ax.annotate(f"n={len(y)}", (0.13, i), fontsize=7.5, color=TEXT_2, va="center")
    ax.set_xscale("log")
    ax.axvline(1, color=MUTED, lw=1, ls="--")
    ax.set_yticks(range(len(order)), order)
    window = ch.get("analysis", "neighbor_window", 10)
    ax.set_xlabel(f"相対再生指数（前後{window}本の中央値=1、対数軸）　橙線=中央値")
    ax.set_title("テーマ別の相対再生指数")
    save(fig, charts / "04_theme_rel.png")

    # テーマ別×期間（交絡確認）
    tp = content.pivot_table(index="theme_name", columns="period", values="rel_index", aggfunc="median").round(2)
    tn = content.pivot_table(index="theme_name", columns="period", values="rel_index", aggfunc="size")
    out += ["### テーマ×期間の相対再生指数中央値（括弧内は本数）", "",
            md_table((tp.astype(str) + " (" + tn.fillna(0).astype(int).astype(str) + ")").reset_index()), ""]


def feature_section(ch, out, content, charts, flags, exclude_label, min_age):
    feats = {**flags, **TITLE_FEATURES}
    res = pd.DataFrame([{**compare_binary(content, f), "label": feats[f]} for f in feats])
    res["p_bh"] = bh_adjust(res["p"])
    res = res[["label", "feature", "n_true", "n_false", "median_true", "median_false", "ratio", "rank_biserial", "p", "p_bh"]]
    scope = f"{exclude_label}を除く通常動画" if exclude_label else "通常動画"
    out += [f"## 4. 内容特徴・タイトル要素と相対再生指数（{scope}・公開{min_age}日以上）", "",
            "Mann-Whitney U 検定、p_bh は Benjamini-Hochberg 補正後", "", md_table(res, "{:.3f}"), ""]
    fig, ax = plt.subplots(figsize=(8, 5))
    r2 = res.sort_values("ratio")
    colors = [SERIES[1] if p < 0.05 else SERIES[0] for p in r2["p_bh"].fillna(1)]
    ax.barh(r2["label"], r2["ratio"] - 1, left=1, color=colors, height=0.6)
    for i, (_, r) in enumerate(r2.iterrows()):
        ax.annotate(f"{r['n_true']}本", (max(r["ratio"], 1) + 0.02, i), va="center", fontsize=7.5, color=TEXT_2)
    ax.axvline(1, color=TEXT_2, lw=1)
    ax.set_xlabel("相対再生指数の中央値の比（該当 / 非該当）　橙=補正後p<0.05")
    ax.set_title("特徴の有無による再生実績の差")
    save(fig, charts / "05_feature_effects.png")


def tone_section(ch, out, content, charts):
    cfg = ch.settings["tone"]
    col = cfg["column"]
    if col not in content:
        return
    tone = content.assign(tone_label=content[col].map(
        {"pos": cfg["pos"], "neg": cfg["neg"], "neu": cfg["neu"]}).fillna(cfg["none"]))
    tg = compare_groups(tone, "tone_label")
    tg.index.name = f"{col}_label"
    out += [f"### {cfg['table_title']}", "", f"Kruskal-Wallis p = {tg.attrs['kruskal_p']:.4f}", "",
            md_table(tg.reset_index()), ""]
    for a, b in [("pos", "neg"), ("pos", "neu")]:
        x = tone.loc[tone[col] == a, "rel_index"]
        y = tone.loc[tone[col] == b, "rel_index"]
        if len(x) and len(y):
            out += [f"- {a} vs {b}: Mann-Whitney p = {stats.mannwhitneyu(x, y).pvalue:.4f}（n={len(x)}, {len(y)}）"]
    out += [""]
    tp2 = tone.pivot_table(index="tone_label", columns="period", values="rel_index", aggfunc="median").round(2)
    tp2.index.name = f"{col}_label"
    out += ["#### 論調×期間の相対再生指数中央値", "", md_table(tp2.reset_index()), ""]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    labels = [cfg["pos"], cfg["neu"], cfg["neg"], cfg["none"]]
    periods = list(tp2.columns)
    w = 0.2
    for i, lab in enumerate(labels):
        vals = [tp2.loc[lab, p] if lab in tp2.index else np.nan for p in periods]
        ns = [int(((tone["tone_label"] == lab) & (tone["period"] == p)).sum()) for p in periods]
        xs = np.arange(len(periods)) + (i - 1.5) * w
        ax.bar(xs, vals, width=w - 0.02, color=SERIES[i], label=lab)
        for x, val, n in zip(xs, vals, ns):
            if val == val:
                ax.annotate(f"{n}", (x, val), xytext=(0, 2), textcoords="offset points", ha="center", fontsize=7, color=TEXT_2)
    ax.axhline(1, color=MUTED, ls="--", lw=1)
    ax.set_xticks(range(len(periods)), periods)
    ax.set_ylabel("相対再生指数の中央値")
    ax.set_title(cfg["chart_title"])
    ax.legend(frameon=False, ncols=2, fontsize=8)
    save(fig, charts / "12_japan_tone.png" if col == "japan_tone" else charts / "12_tone.png")


def title_form_section(out, content):
    sent = compare_groups(content, "form")
    out += ["### タイトルの文型（規則ベース推定）", "", f"Kruskal-Wallis p = {sent.attrs['kruskal_p']:.4f}", "",
            md_table(sent.reset_index()), ""]
    content = content.assign(title_len_bin=pd.cut(content["title_len"], [0, 20, 30, 40, 50, 200],
                                                  labels=["〜20", "20〜30", "30〜40", "40〜50", "50〜"], right=False))
    tl = compare_groups(content, "title_len_bin")
    out += ["### タイトル文字数", "", f"Kruskal-Wallis p = {tl.attrs['kruskal_p']:.4f}", "", md_table(tl.reset_index()), ""]


def regression_section(ch, out, content, flags, labeled):
    """重回帰（交絡の同時調整）"""
    reg = content.dropna(subset=["log_rel"]).copy()
    for c in flags:
        reg[c] = reg[c].fillna(0).astype(int)
    reg["dur_c"] = reg["duration_min"] - reg["duration_min"].mean()
    terms = []
    if labeled and reg["theme"].nunique() > 1:
        ref = ch.get("analysis", "reference_theme") or reg["theme"].mode().iloc[0]
        terms.append(f"C(theme, Treatment('{ref}'))")
    terms += list(flags) + ["has_question_mark", "has_number", "dur_c", "morning_slot"]
    if reg["period"].nunique() > 1:
        terms.append("C(period)")
    formula = "log_rel ~ " + " + ".join(terms)
    n_params = len(smf.ols(formula, data=reg).exog_names) if len(reg) else 0
    if len(reg) < 10 * n_params:
        out += ["### 重回帰", "", f"省略：標本 {len(reg)} 本に対して推定する係数が {n_params} 個あり、"
                f"目安（係数1つあたり10本）に足りない", ""]
        return
    model = smf.ols(formula, data=reg).fit(cov_type="HC3")
    coef = pd.DataFrame({"coef_log2": model.params, "x倍": 2 ** model.params, "p": model.pvalues}).round(3)
    out += ["### 重回帰（目的変数 log2(相対再生指数)、HC3標準誤差）", "",
            f"n = {int(model.nobs)}, 調整済みR² = {model.rsquared_adj:.3f}", "", md_table(coef.reset_index(), "{:.3f}"), ""]


def duration_section(ch, out, vid, content, charts):
    db = compare_groups(content, "dur_bin")
    out += ["## 5. 動画尺", "", f"尺の中央値 {vid['duration_min'].median():.1f}分、平均 {vid['duration_min'].mean():.1f}分", "",
            "### 尺の区分ごとの相対再生指数", "", f"Kruskal-Wallis p = {db.attrs['kruskal_p']:.4f}", "", md_table(db.reset_index()), "",
            "### テーマ別の平均尺", "", md_table(vid.groupby("theme_name")["duration_min"].agg(["size", "mean", "median"]).reset_index()), ""]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    axes[0].hist(vid["duration_min"], bins=np.arange(0, max(36, vid["duration_min"].quantile(0.95) + 2), 1),
                 color=SERIES[0], edgecolor="white")
    axes[0].set_title("動画尺の分布（通常動画）")
    axes[0].set_xlabel("分")
    dm = vid.set_index("pub_jst")["duration_min"]
    axes[1].scatter(dm.index, dm.values, s=10, color=SERIES[0], alpha=0.5, edgecolor="none")
    roll = dm.rolling("21D").median()
    axes[1].plot(roll.index, roll.values, color=SERIES[1], lw=2, label="21日移動中央値")
    style.compact_dates(axes[1], vid["pub_jst"])
    axes[1].set_title("動画尺の推移")
    axes[1].set_ylabel("分")
    axes[1].legend(frameon=False)
    for lab in axes[1].get_xticklabels():
        lab.set_rotation(30)
    save(fig, charts / "06_duration.png")

    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(db.index.astype(str), db["median"], color=SERIES[0], width=0.6)
    for i, (k, r) in enumerate(db.iterrows()):
        ax.annotate(f"n={int(r['n'])}", (i, r["median"]), xytext=(0, 3), textcoords="offset points", ha="center",
                    fontsize=8, color=TEXT_2)
    ax.axhline(1, color=MUTED, ls="--", lw=1)
    ax.set_title("尺の区分ごとの相対再生指数（中央値）")
    save(fig, charts / "07_duration_rel.png")


def posting_section(ch, out, vid, content, charts):
    daily = vid.groupby("date_jst").size()
    slot = slot_label(ch)
    tzl = tz_label(ch)
    out += ["## 6. 投稿戦略", "",
            f"投稿日数 {len(daily)} 日 / 期間 {(vid['pub_jst'].max() - vid['pub_jst'].min()).days + 1} 日、"
            f"1日2本以上の日 {int((daily >= 2).sum())} 日", ""]
    hr = compare_groups(content.assign(slot=np.where(content["morning_slot"], slot, "その他の時間")), "slot")
    out += [f"### 投稿時間帯（{tzl}）", "", md_table(hr.reset_index()), ""]
    per_slot = vid.groupby("period")["morning_slot"].mean().round(2)
    out += [f"### 期間別の{slot}投稿比率", "", md_table(per_slot.reset_index()), ""]
    wd = compare_groups(content.assign(weekday_name=content["weekday"].map(dict(enumerate("月火水木金土日")))), "weekday_name")
    out += ["### 曜日", "", f"Kruskal-Wallis p = {wd.attrs['kruskal_p']:.4f}", "", md_table(wd.reset_index()), ""]

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    hc = vid.groupby("hour_jst").size().reindex(range(24), fill_value=0)
    axes[0].bar(hc.index, hc.values, color=SERIES[0], width=0.7)
    axes[0].set_title(f"投稿時刻の分布（{tzl}）")
    axes[0].set_xticks(range(0, 24, 3))
    pc = vid.groupby(["period"]).apply(lambda x: x.groupby("date_jst").size().mean(), include_groups=False)
    axes[1].bar(pc.index, pc.values, color=SERIES[0], width=0.6)
    axes[1].set_title("投稿日あたりの平均本数（期間別）")
    save(fig, charts / "08_posting.png")

    # 同日の追加投稿が定時枠の動画を食うか（直近2期間）
    vid["n_same_day"] = vid.groupby("date_jst")["video_id"].transform("size")
    periods = sorted(vid["period"].unique())
    last2 = periods[-2:][::-1]
    cann = pd.concat([vid[vid["morning_slot"] & vid["mature"] & (vid["period"] == p)] for p in last2])
    cann = cann.assign(same_day=lambda x: np.where(x["n_same_day"] >= 2, "同日に他の投稿あり", "単独"))
    names = "・".join(p.split()[0] for p in last2[::-1])
    if len(cann):
        head = "朝" if slot.startswith("朝") else "定時枠"
        out += [f"### {head}の動画：同日に他の投稿がある場合（{names}）", "",
                md_table(compare_groups(cann, "same_day").reset_index()), ""]

    # シリーズ・型
    srows = []
    for name, pat in ch.settings.get("series", {}).items():
        m = vid[vid["title"].str.contains(pat, regex=True)]
        mm = m[m["mature"]]
        srows.append({"型": name, "本数": len(m), "初出": m["published_jst"].min()[:10] if len(m) else "",
                      "相対指数中央値": mm["rel_index"].median(), "再生中央値": mm["views"].median()})
    if srows:
        out += ["### シリーズ・タイトルの型", "", md_table(pd.DataFrame(srows), "{:,.2f}"), ""]


def accumulation_section(ch, out, vid, snaps):
    if not len(snaps):
        return
    sv = snaps.merge(vid[["video_id", "views", "published_at", "title"]], on="video_id", how="inner",
                     suffixes=("_snap", "_now"))
    sv["age_at_snap_d"] = (sv["snapshot_at"] - sv["published_at"]).dt.total_seconds() / 86400
    sv = sv[sv["age_at_snap_d"] > 0].sort_values("age_at_snap_d")
    sv["share_of_now"] = sv["views_snap"] / sv["views_now"]
    sv = sv.drop_duplicates("video_id")
    bins = pd.cut(sv["age_at_snap_d"], [0, 1, 3, 7, 14, 30, 90], labels=["〜1日", "1〜3日", "3〜7日", "7〜14日", "14〜30日", "30〜90日"])
    acc = sv.groupby(bins, observed=True)["share_of_now"].agg(["size", "median"])
    out += ["## 8. 再生数の蓄積速度（Wayback の動画一覧に表示された再生数 / 現在の再生数）", "",
            "公開からの経過日数ごとに、当時の再生数が現在の何割だったか（動画ごとに最初の観測のみ）", "",
            md_table(acc.reset_index(), "{:.2f}"), ""]
    sv.to_csv(ch.processed_dir / "view_accumulation.csv", index=False)


if __name__ == "__main__":
    main()
