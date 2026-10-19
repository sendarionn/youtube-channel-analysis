"""サムネイルや映像フレームの一覧画像（コンタクトシート）を作る"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..analyze.thumbnail_features import crop_16x9

FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/opt/X11/share/system_fonts/ヒラギノ角ゴシック W6.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def load_font(size: int):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def contact_sheet(items: list[tuple[Path, str]], out: Path, cols: int = 4, cell_w: int = 320,
                  label_h: int = 44, crop: bool = True) -> Path:
    """items: (画像パス, ラベル) のリスト。ラベルは2行まで表示する"""
    cell_h = round(cell_w * 9 / 16)
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows * (cell_h + label_h)), "white")
    draw = ImageDraw.Draw(sheet)
    font = load_font(13)
    for i, (path, label) in enumerate(items):
        x, y = (i % cols) * cell_w, (i // cols) * (cell_h + label_h)
        im = Image.open(path).convert("RGB")
        im = (crop_16x9(im) if crop else im).resize((cell_w, cell_h))
        sheet.paste(im, (x, y))
        lines = label.split("\n")[:2]
        for k, line in enumerate(lines):
            draw.text((x + 4, y + cell_h + 3 + k * 18), line[:26], fill="black", font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=85)
    return out
