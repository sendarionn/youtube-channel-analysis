"""Phase 3: 代表動画の自動計測（字幕・カット検出）と目視用資料の生成

使い方:
    python -m ycanalysis.analyze.phase3 <slug> metrics   # 計測値を processed/phase3_metrics.csv に保存
    python -m ycanalysis.analyze.phase3 <slug> dossier --vid=ID  # 1本分の目視用資料（冒頭・分ごと要約・終盤）を表示
    python -m ycanalysis.analyze.phase3 <slug> sheet --vid=ID [--every 30]  # フレーム一覧画像を作る
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from ..config import load_channel
from ..visualize.contact_sheet import contact_sheet
from .transcript import first_time, load_json3, minute_blocks, speech_stats, text_between

# チャンネル固有の挨拶・定型句（config に移すほどの汎用性はまだないため、ここで定義）
PATTERNS = {
    "t_channel_intro": r"海外\s*(?:[YyＹ]|ワイ)?\s*パ\s*パ?\s*(?:ラジオ|です)|海外ワイパ|how\s*are|ハウアー|ハワユ|ハウアユ",
    "t_today": r"今日は|今回は|本日は",
    "t_conclusion": r"結論|まとめると|つまり|要するに",
    "t_first_cta": r"チャンネル登録|高評価",
    "t_roadmap": r"[2-5２-５二三四五]つ(?:あって|です|に分けて|見ていきます|話します|の(?:ブロック|話|順番|ポイント|柱))|[2-5２-５]つの(?:ブロック|順番)",
    "t_callback": r"(?:最初|冒頭)の(?:問い?|疑問|数字|話)に戻",
}


def subs_path(ch, vid: str) -> Path | None:
    for name in (f"{vid}.ja.json3", f"{vid}.ja-orig.json3"):
        p = ch.raw_dir / "subs" / name
        if p.exists():
            return p
    return None


def metrics(ch) -> pd.DataFrame:
    sample = pd.read_csv(ch.processed_dir / "phase3_sample.csv")
    v = pd.read_csv(ch.processed_dir / "analysis_videos.csv").set_index("video_id")
    extra = [vid for vid in json.loads((ch.data_dir / "annotations" / "phase3_extra.json").read_text())]
    ids = list(sample["video_id"]) + [x for x in extra if x not in set(sample["video_id"])]
    rows = []
    for vid in ids:
        dur = float(v.loc[vid, "duration_s"])
        row = {"video_id": vid, "tier": sample.set_index("video_id")["tier"].get(vid, "extra"),
               "title": v.loc[vid, "title"], "duration_min": dur / 60, "rel_index": v.loc[vid, "rel_index"]}
        sp = subs_path(ch, vid)
        if sp:
            segs = load_json3(sp)
            row.update(speech_stats(segs, dur))
            row.update({k: first_time(segs, p) for k, p in PATTERNS.items()})
        cp = ch.raw_dir / "scene_cuts" / f"{vid}.json"
        if cp.exists():
            cuts = json.loads(cp.read_text())["cuts"]
            row["cuts"] = len(cuts)
            row["cuts_per_min"] = len(cuts) / (dur / 60)
            row["cuts_first_60s"] = sum(c < 60 for c in cuts)
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(ch.processed_dir / "phase3_metrics.csv", index=False)
    timeline_chart(ch, df)
    return df


def timeline_chart(ch, df: pd.DataFrame) -> Path:
    """全サンプルの構成要素の出現位置（分）を群ごとに並べる"""
    from ..visualize import style
    from ..visualize.style import MUTED, SERIES, TEXT_2, plt, save
    style.setup()
    order = {"high": 0, "extra": 1, "mid": 2, "low": 3}
    d = df.assign(o=df["tier"].map(order)).sort_values(["o", "rel_index"], ascending=[True, False]).reset_index(drop=True)
    marks = [("t_channel_intro", "チャンネル紹介", SERIES[0], "o"), ("t_roadmap", "構成の予告", SERIES[2], "s"),
             ("t_callback", "冒頭への回帰", SERIES[6], "D"), ("t_first_cta", "登録・高評価の依頼", SERIES[1], "v")]
    fig, ax = plt.subplots(figsize=(9, 10))
    for i, r in d.iterrows():
        ax.plot([0, r["duration_min"]], [i, i], color=MUTED, lw=1.5, solid_capstyle="round")
        if r["cuts_per_min"] == r["cuts_per_min"]:
            pass
    for col, label, color, m in marks:
        ax.scatter(d[col] / 60, d.index, color=color, marker=m, s=34, label=label, zorder=3, edgecolor="white", linewidth=1)
    ax.set_yticks(d.index, [f"{r['tier']} {r['rel_index']:.2f} {str(r['title'])[:14]}" for _, r in d.iterrows()], fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlabel("分")
    ax.set_title("構成要素の出現位置（字幕から自動検出）")
    ax.legend(frameon=False, loc="lower right", fontsize=8)
    return save(fig, ch.report_dir / "charts" / "11_structure_timelines.png")


def _videos(ch) -> pd.DataFrame:
    p = ch.processed_dir / "analysis_videos.csv"
    if p.exists():
        return pd.read_csv(p).set_index("video_id")
    from .build_dataset import load_videos  # 比較チャンネルは Phase 2 を通さないため raw から読む
    return load_videos(ch)[0].set_index("video_id")


def dossier(ch, vid: str, head_chars: int = 70) -> str:
    v = _videos(ch)
    dur = float(v.loc[vid, "duration_s"])
    segs = load_json3(subs_path(ch, vid))
    lines = [f"# {v.loc[vid, 'title']} ({dur / 60:.1f}分, 指数 {v.loc[vid, 'rel_index']:.2f})", "",
             "## 冒頭90秒", text_between(segs, 0, 90), "", "## 分ごとの冒頭"]
    for t, txt in minute_blocks(segs, dur):
        lines.append(f"{int(t // 60):02d}:00 {txt[:head_chars]}")
    lines += ["", "## 終盤60秒", text_between(segs, dur - 60, dur + 1)]
    return "\n".join(lines)


def sheet(ch, vid: str, every: int) -> Path:
    fdir = ch.raw_dir / "frames" / vid
    meta = json.loads((ch.raw_dir / "scene_cuts" / f"{vid}.json").read_text())
    step = max(1, every // meta["frame_every_s"])
    frames = sorted(fdir.glob("f_*.jpg"))[::step]
    items = [(f, f"{(i * every) // 60}:{(i * every) % 60:02d}") for i, f in enumerate(frames)]
    return contact_sheet(items, ch.raw_dir / "frames" / f"{vid}_sheet.jpg", cols=8, cell_w=200, label_h=18, crop=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("cmd", choices=["metrics", "dossier", "sheet"])
    ap.add_argument("--vid", help='"-" で始まる ID は --vid=ID の形で渡す')
    ap.add_argument("--every", type=int, default=30)
    a = ap.parse_args()
    ch = load_channel(a.slug)
    if a.cmd == "metrics":
        print(metrics(ch).round(2).to_string())
    elif a.cmd == "dossier":
        print(dossier(ch, a.vid))
    else:
        print(sheet(ch, a.vid, a.every))


if __name__ == "__main__":
    main()
