"""サムネイル画像の客観特徴量

- brightness: 明度（HSV の V）の平均
- saturation: 彩度の平均
- colorfulness: Hasler & Süsstrunk (2003) の colorfulness 指標
- edge_density: 輝度差の大きい画素の割合（情報密度の近似）
- yellow_ratio / red_ratio / blue_ratio: 色相帯ごとの高彩度画素の割合
- text_like_ratio: 高コントラストの白・黄・橙画素の割合（大きな文字の近似）

hqdefault は 4:3 の上下に黒帯を含むため、16:9 部分を切り出して計算する
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def crop_16x9(im: Image.Image) -> Image.Image:
    w, h = im.size
    target_h = round(w * 9 / 16)
    if target_h < h:
        top = (h - target_h) // 2
        return im.crop((0, top, w, top + target_h))
    return im


def image_features(im: Image.Image) -> dict:
    im = crop_16x9(im.convert("RGB")).resize((320, 180))
    rgb = np.asarray(im, dtype=float)
    hsv = np.asarray(im.convert("HSV"), dtype=float)
    h, s, v = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    rg, yb = r - g, 0.5 * (r + g) - b
    colorfulness = np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean())
    gray = rgb.mean(axis=2)
    gx, gy = np.abs(np.diff(gray, axis=1))[:-1], np.abs(np.diff(gray, axis=0))[:, :-1]
    edges = (gx + gy) > 60
    vivid = s > 0.5
    return {
        "brightness": float(v.mean()),
        "saturation": float(s.mean()),
        "colorfulness": float(colorfulness),
        "edge_density": float(edges.mean()),
        "yellow_ratio": float((vivid & (h >= 40) & (h < 70) & (v > 0.6)).mean()),
        "orange_ratio": float((vivid & (h >= 15) & (h < 40) & (v > 0.6)).mean()),
        "red_ratio": float((vivid & ((h < 15) | (h >= 340))).mean()),
        "blue_ratio": float((vivid & (h >= 190) & (h < 260)).mean()),
        "text_like_ratio": float((((s < 0.15) & (v > 0.92)) | (vivid & (h >= 15) & (h < 70) & (v > 0.75))).mean()),
    }


def features_for_dir(d: Path) -> list[dict]:
    return [{"video_id": p.stem, **image_features(Image.open(p))} for p in sorted(d.glob("*.jpg"))]
