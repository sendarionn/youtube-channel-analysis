"""チャンネル設定とパスの解決"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Channel:
    slug: str
    name: str
    handle: str
    channel_id: str
    url: str
    lang: str = "ja"

    @property
    def data_dir(self) -> Path:
        return ROOT / "data" / self.slug

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def report_dir(self) -> Path:
        return ROOT / "reports" / self.slug


def load_channel(slug: str) -> Channel:
    path = ROOT / "config" / "channels" / f"{slug}.toml"
    with path.open("rb") as f:
        return Channel(**tomllib.load(f))
