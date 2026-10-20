import json
import sys
from types import SimpleNamespace

from ycanalysis import research


def test_url_starts_existing_channel_update(monkeypatch, tmp_path, capsys):
    called = {}

    def run(cmd):
        called["cmd"] = cmd
        return SimpleNamespace(returncode=0)
    (tmp_path / "research_status.json").write_text(json.dumps(
        {"state": "quantitative_complete", "next_actions": ["内容分析"]}))
    monkeypatch.setattr(research, "initialize", lambda url, slug, lang: ("existing", False))
    monkeypatch.setattr(research, "load_channel", lambda slug: SimpleNamespace(report_dir=tmp_path))
    monkeypatch.setattr(research.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["research", "https://youtube.com/@example", "--no-wayback"])
    research.main()
    assert called["cmd"][-3:] == ["existing", "--collect", "--no-wayback"]
    out = capsys.readouterr().out
    assert "調査状態: quantitative_complete" in out and "未完成" in out and "分析完了" not in out
