"""手作業コーディングの補助（盲検用シートの出力と一致率の計算）

再生数・公開日・既存のラベルを含まないシートを、乱数で並べ替えて出力する
コーダー（人間または AI）はシートだけを見て判定し、その結果を既存ラベルと比較する

使い方:
    python -m ycanalysis.annotate <slug> export [--columns theme,japan_angle,...] [--seed 0]
        → data/<slug>/annotations/blind/sheet_<日付>.csv
    python -m ycanalysis.annotate <slug> agreement <再判定したCSV> [--against labels_manual.csv]
        → 列ごとの一致率と Cohen's κ
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .config import load_channel


def cohen_kappa_nominal(a: pd.Series, b: pd.Series) -> float:
    """名義尺度（テーマなど多値も可）の Cohen's κ"""
    a, b = a.astype(str), b.astype(str)
    cats = sorted(set(a) | set(b))
    po = (a == b).mean()
    pe = sum((a == c).mean() * (b == c).mean() for c in cats)
    return float((po - pe) / (1 - pe)) if pe < 1 else float("nan")


def export(ch, columns: list[str], seed: int) -> Path:
    v = pd.read_csv(ch.processed_dir / "videos.csv")
    sheet = v[["video_id", "title"]].sample(frac=1, random_state=seed).reset_index(drop=True)
    for c in columns:
        sheet[c] = ""
    d = ch.annotations_dir / "blind"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"sheet_{date.today():%Y%m%d}_seed{seed}.csv"
    sheet.to_csv(path, index=False)
    return path


def agreement(ch, recoded: Path, against: str) -> pd.DataFrame:
    a = pd.read_csv(ch.annotations_dir / against)
    b = pd.read_csv(recoded)
    m = a.merge(b, on="video_id", suffixes=("", "_re"))
    rows = []
    for c in [c for c in b.columns if c not in ("video_id", "title") and c in a.columns]:
        x, y = m[c].fillna("NA"), m[f"{c}_re"].fillna("NA")
        rows.append({"column": c, "n": len(m), "一致率": float((x.astype(str) == y.astype(str)).mean()),
                     "kappa": cohen_kappa_nominal(x, y)})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("cmd", choices=["export", "agreement"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--columns", default="theme")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--against", default="labels_manual.csv")
    a = ap.parse_args()
    ch = load_channel(a.slug)
    if a.cmd == "export":
        print(export(ch, a.columns.split(","), a.seed))
    else:
        res = agreement(ch, Path(a.file), a.against)
        print(res.round(3).to_string(index=False))
        print("\n目安：κ ≥ 0.8 ほぼ一致、0.6〜0.8 実質的に一致、0.4〜0.6 中程度、0.4 未満は基準の見直しが必要")


if __name__ == "__main__":
    main()
