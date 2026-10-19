"""raw データの保存

取得ごとにタイムスタンプ付きディレクトリを作り、既存データを上書きしない
各ディレクトリに manifest.json（出典・取得日時・方法）を置く
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_snapshot_dir(raw_dir: Path, kind: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    d = raw_dir / kind / stamp
    d.mkdir(parents=True, exist_ok=False)
    return d


def write_manifest(d: Path, **info) -> None:
    info.setdefault("retrieved_at", utc_now())
    (d / "manifest.json").write_text(json.dumps(info, ensure_ascii=False, indent=2))


def latest_snapshot_dir(raw_dir: Path, kind: str) -> Path:
    dirs = sorted(p for p in (raw_dir / kind).iterdir() if p.is_dir())
    if not dirs:
        raise FileNotFoundError(f"{raw_dir / kind} にスナップショットがない")
    return dirs[-1]


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
