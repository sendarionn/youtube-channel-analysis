"""内容分析用に、選定した動画の低解像度映像を一時取得し、フレームとカット情報を抽出する

著作権・容量に配慮し、映像は 360p 以下で取得し、抽出後に削除する（--keep で保持）
保存するのはカット時刻（テキスト）と縮小フレームのみで、いずれも Git 管理外

使い方:
    python -m ycanalysis.collect.media_sample <slug> ID [ID ...] [--every 15]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import subprocess
import time
from pathlib import Path

import yt_dlp

from ..config import load_channel
from .rawstore import utc_now

SCENE_THRESHOLD = 0.3


def download(vid: str, d: Path, lang: str) -> Path:
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "format": "bv*[height<=360]+ba/b[height<=360]/wv*+wa",
            "merge_output_format": "mp4", "outtmpl": str(d / "%(id)s.%(ext)s"),
            "extractor_args": {"youtube": {"lang": [lang]}}}
    # JS ランタイムがないと一部の形式が取得できず 403 になるため、node があれば使う
    if shutil.which("node"):
        opts["js_runtimes"] = {"node": {}}
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={vid}"])
    return next(d.glob(f"{vid}.*"))


def scene_cuts(path: Path, threshold: float = SCENE_THRESHOLD) -> list[float]:
    """ffmpeg のシーン変化検出でカット時刻（秒）を得る"""
    cmd = ["ffmpeg", "-hide_banner", "-i", str(path), "-an", "-vf",
           f"scale=160:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"]
    err = subprocess.run(cmd, capture_output=True, text=True).stderr
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", err)]


def extract_frames(path: Path, out: Path, every: int) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-vf",
                    f"fps=1/{every},scale=320:-2", "-q:v", "5", str(out / "f_%04d.jpg")], check=True)
    return sorted(out.glob("f_*.jpg"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--every", type=int, default=15, help="フレーム抽出間隔（秒）")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    ch = load_channel(a.slug)
    media, frames, cuts_dir = ch.raw_dir / "media", ch.raw_dir / "frames", ch.raw_dir / "scene_cuts"
    for d in (media, frames, cuts_dir):
        d.mkdir(parents=True, exist_ok=True)
    for vid in a.ids:
        cut_path = cuts_dir / f"{vid}.json"
        if cut_path.exists() and (frames / vid).exists():
            continue
        try:
            path = download(vid, media, ch.lang)
        except yt_dlp.utils.DownloadError as e:
            print(vid, "失敗", e)
            continue
        cuts = scene_cuts(path)
        extract_frames(path, frames / vid, a.every)
        cut_path.write_text(json.dumps({"video_id": vid, "threshold": SCENE_THRESHOLD, "cuts": cuts,
                                        "frame_every_s": a.every, "retrieved_at": utc_now(),
                                        "method": "yt-dlp <=360p + ffmpeg select=gt(scene,t)"}, indent=1))
        if not a.keep:
            path.unlink()
        print(vid, len(cuts), "cuts")
        time.sleep(5 + random.random() * 3)


if __name__ == "__main__":
    main()
