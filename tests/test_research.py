import sys
from types import SimpleNamespace

from ycanalysis import research


def test_url_starts_existing_channel_update(monkeypatch):
    called = {}
    def run(cmd):
        called["cmd"] = cmd
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(research, "initialize", lambda url, slug, lang: ("existing", False))
    monkeypatch.setattr(research.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["research", "https://youtube.com/@example", "--no-wayback"])
    research.main()
    assert called["cmd"][-3:] == ["existing", "--collect", "--no-wayback"]
