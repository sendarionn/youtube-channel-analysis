"""品質ゲートと調査状態の回帰テスト（未完成の調査を完成扱いにしない）"""
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from ycanalysis.analyze import finalize, quality_gate

SUBS = 251000


def make_channel(tmp_path):
    ch = SimpleNamespace(slug="test", channel_id="UCtarget", name="テスト", settings={},
                         report_dir=tmp_path / "reports", annotations_dir=tmp_path / "annotations",
                         processed_dir=tmp_path / "processed", raw_dir=tmp_path / "raw")
    for p in (ch.report_dir, ch.annotations_dir, ch.processed_dir, ch.raw_dir / "subs", ch.raw_dir / "frames"):
        p.mkdir(parents=True)
    return ch


def quantitative(ch):
    (ch.report_dir / "phase2_tables.md").write_text("done")
    pd.DataFrame({"video_id": ["a"] + [f"abcdefghi{i:02d}" for i in range(10)]}).to_csv(
        ch.processed_dir / "analysis_videos.csv", index=False)
    pd.DataFrame({"video_id": ["a"]}).to_csv(ch.processed_dir / "videos.csv", index=False)
    pd.DataFrame([{"snapshot_at": "2026-10-20", "file": "x_about.html", "subscriber_text": "251K subscribers",
                   "subscribers": SUBS, "subscriber_source": "channel_id_node", "identity_validated": True,
                   "subscriber_precision": "rounded_display", "video_count": 100, "total_views": 1,
                   "status": "有効", "note": "", "source": "direct"}]).to_csv(
        ch.processed_dir / "subscriber_audit.csv", index=False)
    (ch.processed_dir / "build_info.json").write_text(json.dumps({"videos_source": {}, "kinds": {"video": 100}}))
    pd.DataFrame({"title": ["人口50万人都市"], "accepted": [False]}).to_csv(
        ch.processed_dir / "milestone_candidates.csv", index=False)


def full_evidence(ch, root):
    (ch.annotations_dir / "external_checks.json").write_text(json.dumps(
        [{"source": "ユーチュラ", "subscribers": 251000, "retrieved_at": "2026-10-19", "channel_id_confirmed": True}]))
    (ch.annotations_dir / "theme_validation.json").write_text(json.dumps(
        {"validated": True, "n_checked": 60, "kappa": 0.75}))
    ids = [f"v{i:02d}" for i in range(12)]
    pd.DataFrame({"video_id": ids, "tier": ["high"] * 6 + ["low"] * 6}).to_csv(
        ch.annotations_dir / "phase3_coding.csv", index=False)
    for v in ids:
        (ch.raw_dir / "subs" / f"{v}.ja.json3").write_text("{}")
        (ch.raw_dir / "frames" / v).mkdir()
    (ch.report_dir / "phase4_tables.md").write_text("| 指標 | 対象 | 比較A | 比較B |\n|---|---|---|---|\n")
    hyp = "\n".join(f"## H{i} 仮説\n- 支持 x\n- 反証 x\n- 代替説明 x\n- 確信度 中\n- 再現可能性 中" for i in range(1, 4))
    (ch.report_dir / "hypotheses.md").write_text(hyp)
    urls = "\n".join(f"- https://www.youtube.com/watch?v=abcdefghi{i:02d}" for i in range(10))
    body = {1: "- 【事実】登録者 251,000人\n- 【推論】確信度 中", 6: "比較チャンネルの選定理由。" + "x" * 400,
            7: "発見 クリック 継続 再訪", 8: "- a\n- b\n- c", 9: "- a\n- b\n- c"}
    text = "\n\n".join(f"## {i}. 見出し\n\n{body.get(i, '本文')}" for i in range(1, 10)) + "\n" + urls
    (ch.report_dir / "DRAFT_REPORT.md").write_text(text)
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "test-analysis.md").write_text("## 調査目的\n\n" + "交通解説チャンネルの成長要因を検証済みの登録者推移から調べる。" * 2)


@pytest.fixture
def env(tmp_path, monkeypatch):
    ch = make_channel(tmp_path)
    monkeypatch.setattr(quality_gate, "load_channel", lambda slug: ch)
    monkeypatch.setattr(quality_gate, "record_run", lambda *a, **k: None)
    monkeypatch.setattr(quality_gate, "ROOT", tmp_path)
    monkeypatch.setattr(finalize, "load_channel", lambda slug: ch)
    monkeypatch.setattr(finalize, "record_run", lambda *a, **k: None)
    return ch, tmp_path


def test_collecting_before_data(env):
    ch, _ = env
    assert quality_gate.evaluate("test")["state"] == "collecting"


def test_quantitative_only_is_not_complete(env):
    ch, _ = env
    quantitative(ch)
    r = quality_gate.evaluate("test")
    assert r["state"] == "quantitative_complete"
    for k in ("tier_comparison", "peer_comparison", "hypotheses_validated", "no_placeholders"):
        assert k in r["missing"]


def test_full_evidence_is_complete_and_finalizes(env, monkeypatch):
    ch, root = env
    quantitative(ch)
    full_evidence(ch, root)
    r = quality_gate.evaluate("test")
    assert r["state"] == "complete", r["missing"]
    monkeypatch.setattr("sys.argv", ["finalize", "test"])
    finalize.main()
    assert (ch.report_dir / "FINAL_REPORT.md").read_text() == (ch.report_dir / "DRAFT_REPORT.md").read_text()


@pytest.mark.parametrize("breaker,missing", [
    (lambda ch: (ch.annotations_dir / "phase3_coding.csv").unlink(), "tier_comparison"),
    (lambda ch: (ch.report_dir / "phase4_tables.md").unlink(), "peer_comparison"),
    (lambda ch: (ch.report_dir / "hypotheses.md").write_text("## H1 仮説\n- 支持 x"), "hypotheses_validated"),
    (lambda ch: (ch.report_dir / "DRAFT_REPORT.md").write_text(
        (ch.report_dir / "DRAFT_REPORT.md").read_text() + "\n（要記入）"), "no_placeholders"),
    (lambda ch: [p.rmdir() for p in (ch.raw_dir / "frames").iterdir()], "subtitles_and_video_checked"),
])
def test_missing_required_step_is_not_complete(env, breaker, missing):
    ch, root = env
    quantitative(ch)
    full_evidence(ch, root)
    breaker(ch)
    r = quality_gate.evaluate("test")
    assert r["state"] != "complete" and missing in r["missing"]


def test_large_external_divergence_fails(env):
    ch, root = env
    quantitative(ch)
    full_evidence(ch, root)
    (ch.annotations_dir / "external_checks.json").write_text(json.dumps(
        [{"source": "外部", "subscribers": 17700, "channel_id_confirmed": True}]))
    r = quality_gate.evaluate("test")
    assert "cross_source" in r["missing"]


def test_failed_step_and_blocked_states(env):
    ch, root = env
    quantitative(ch)
    (ch.report_dir / "run_info.json").write_text(json.dumps({"run:quant": {"status": "failed"}}))
    assert quality_gate.evaluate("test")["state"] == "failed"
    (ch.report_dir / "run_info.json").write_text("{}")
    (ch.annotations_dir / "blocked.json").write_text(json.dumps({"subtitles": "字幕が公開されていない"}))
    assert quality_gate.evaluate("test")["state"] == "blocked"


def test_incomplete_report_is_not_finalized_and_existing_final_preserved(env, monkeypatch):
    ch, _ = env
    quantitative(ch)
    (ch.report_dir / "FINAL_REPORT.md").write_text("旧版")
    (ch.report_dir / "DRAFT_REPORT.md").write_text("要記入")
    monkeypatch.setattr("sys.argv", ["finalize", "test"])
    finalize.main()
    assert (ch.report_dir / "FINAL_REPORT.md").read_text() == "旧版"


def test_complete_report_archives_previous_final(env, monkeypatch):
    ch, root = env
    quantitative(ch)
    full_evidence(ch, root)
    (ch.report_dir / "FINAL_REPORT.md").write_text("旧版")
    monkeypatch.setattr("sys.argv", ["finalize", "test"])
    finalize.main()
    arch = list((ch.report_dir / "archive").glob("FINAL_REPORT-*.md"))
    assert len(arch) == 1 and arch[0].read_text() == "旧版"


def test_status_preserves_step_records_for_resume(env):
    ch, _ = env
    quantitative(ch)
    (ch.report_dir / "research_status.json").write_text(json.dumps({"steps": {"quant": {"status": "ok"}}}))
    r = quality_gate.evaluate("test")
    assert r["steps"]["quant"]["status"] == "ok"


def test_external_value_compared_with_nearest_observation(env):
    ch, root = env
    quantitative(ch)
    full_evidence(ch, root)
    a = pd.read_csv(ch.processed_dir / "subscriber_audit.csv")
    old = a.iloc[0].copy()
    old["snapshot_at"], old["subscribers"], old["source"], old["file"] = "2025-06-07", 205000, "wayback", "w.html"
    pd.concat([pd.DataFrame([old]), a]).to_csv(ch.processed_dir / "subscriber_audit.csv", index=False)
    (ch.annotations_dir / "external_checks.json").write_text(json.dumps(
        [{"source": "vidIQ", "subscribers": 205000, "as_of": "2025-06-03", "channel_id_confirmed": True}]))
    r = quality_gate.evaluate("test")
    assert r["checks"]["cross_source"]["ok"], r["checks"]["cross_source"]


def test_unknown_cited_video_fails(env):
    ch, root = env
    quantitative(ch)
    full_evidence(ch, root)
    p = ch.report_dir / "DRAFT_REPORT.md"
    p.write_text(p.read_text() + "\n- https://www.youtube.com/watch?v=XXXXXXXXXXX")
    r = quality_gate.evaluate("test")
    assert "cited_videos_exist" in r["missing"]


def test_placeholder_pattern_ignores_normal_words():
    assert not quality_gate.PLACEHOLDERS.search("結論（要約）を先に書く")
    assert quality_gate.PLACEHOLDERS.search("（要記入：問い）")
    assert quality_gate.PLACEHOLDERS.search("{summary}")


def test_research_question_accepts_numbered_heading(env):
    ch, root = env
    quantitative(ch)
    full_evidence(ch, root)
    (root / "docs" / "test-analysis.md").write_text("## 1. 目的\n\n" + "対象チャンネルの成長要因を公開データと内容分析で明らかにする。" * 2)
    assert quality_gate.evaluate("test")["checks"]["research_question"]["ok"]
