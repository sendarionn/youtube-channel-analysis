"""YouTubeチャンネルURLの検証と正規化"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse


CHANNEL_ID = re.compile(r"^UC[A-Za-z0-9_-]{20,}$")


@dataclass(frozen=True)
class ChannelURL:
    original: str
    canonical: str
    kind: str
    value: str


def parse_channel_url(value: str) -> ChannelURL:
    raw = value.strip()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower()
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        raise ValueError("YouTubeのチャンネルURLではありません")
    parts = [unquote(p) for p in parsed.path.split("/") if p]
    if not parts or parts[0] in {"watch", "playlist", "shorts", "live"}:
        raise ValueError("動画または再生リストではなくチャンネルURLを指定してください")
    first = parts[0]
    if first.startswith("@") and len(parts) == 1 and len(first) > 1:
        return ChannelURL(raw, f"https://www.youtube.com/{first}", "handle", first)
    if first in {"channel", "user", "c"} and len(parts) == 2 and parts[1]:
        if first == "channel" and not CHANNEL_ID.fullmatch(parts[1]):
            raise ValueError("チャンネルIDの形式が不正です")
        return ChannelURL(raw, f"https://www.youtube.com/{first}/{parts[1]}", first, parts[1])
    raise ValueError("対応していないYouTube URLです")
