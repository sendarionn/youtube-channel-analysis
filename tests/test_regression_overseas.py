"""海外Yパパの既存分析の回帰テスト

リポジトリ内の raw（ytdlp_videos）と processed、methodology/baselines を使う
データがない環境ではスキップする
"""
import json

import pandas as pd
import pytest

from ycanalysis.analyze.baseline import compare, key_results, path
from ycanalysis.analyze.build_dataset import load_videos
from ycanalysis.config import load_channel

ch = load_channel("overseas-y-papa")
needs_data = pytest.mark.skipif(not (ch.processed_dir / "analysis_videos.csv").exists()
                                or not (ch.raw_dir / "ytdlp_videos").exists(), reason="データなし")


@needs_data
def test_raw_reproduces_processed_videos():
    df, _ = load_videos(ch)
    stored = pd.read_csv(ch.processed_dir / "videos.csv")
    assert len(df) == len(stored) == 351
    m = df.merge(stored, on="video_id", suffixes=("", "_s"))
    for col in ["views", "duration_s", "rel_index", "title_len"]:
        assert (m[col] - m[f"{col}_s"]).abs().max() < 1e-9, col


@needs_data
def test_key_results_match_baseline():
    expected = json.loads(path("overseas-y-papa").read_text())
    assert compare(expected, key_results(ch)) == []


@needs_data
def test_key_findings_direction():
    # 報告書の主要な結論（国際比較・日本との結びつきは高い、疑問符は差なし）
    r = key_results(ch)
    assert r["ratio:intl_compare"] > 1.5 and r["p:intl_compare"] < 0.01
    assert r["ratio:japan_angle"] > 1.2 and r["p:japan_angle"] < 0.01
    assert r["p:has_question_mark"] > 0.05
