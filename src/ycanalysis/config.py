"""チャンネル設定とパスの解決

config/channels/<slug>.toml のうち、識別情報（slug・name・handle・channel_id・url・lang）以外の
表（[analysis]・[themes] など）は settings に入る。項目の意味は templates/channel-config.toml を参照
"""
from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import METHODOLOGY_VERSION

ROOT = Path(__file__).resolve().parents[2]
# 回帰確認用：設定すると processed/ と reports/ だけをこの下に書き出し、既存の成果物を上書きしない
OUTPUT_ROOT_ENV = "YCANALYSIS_OUTPUT_ROOT"


def output_root() -> Path:
    return Path(os.environ[OUTPUT_ROOT_ENV]) if os.environ.get(OUTPUT_ROOT_ENV) else ROOT


IDENTITY_KEYS = ("slug", "name", "handle", "channel_id", "url", "lang")


@dataclass(frozen=True)
class Channel:
    slug: str
    name: str
    handle: str
    channel_id: str
    url: str
    lang: str = "ja"
    settings: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def data_dir(self) -> Path:
        return ROOT / "data" / self.slug

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return output_root() / "data" / self.slug / "processed"

    @property
    def annotations_dir(self) -> Path:
        return self.data_dir / "annotations"

    @property
    def report_dir(self) -> Path:
        return output_root() / "reports" / self.slug

    @property
    def timezone(self) -> str:
        return self.settings.get("timezone", "Asia/Tokyo")

    def get(self, section: str, key: str, default=None):
        return self.settings.get(section, {}).get(key, default)


def load_channel(slug: str) -> Channel:
    path = ROOT / "config" / "channels" / f"{slug}.toml"
    with path.open("rb") as f:
        raw = tomllib.load(f)
    ident = {k: raw.pop(k) for k in IDENTITY_KEYS if k in raw}
    return Channel(**ident, settings=raw)


def record_run(ch: Channel, step: str, **info) -> None:
    """どの方法論バージョンで各工程を実行したかを reports/<slug>/run_info.json に追記する"""
    path = ch.report_dir / "run_info.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    runs = json.loads(path.read_text()) if path.exists() else {}
    runs[step] = {"methodology_version": METHODOLOGY_VERSION,
                  "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **info}
    path.write_text(json.dumps(runs, ensure_ascii=False, indent=2))
