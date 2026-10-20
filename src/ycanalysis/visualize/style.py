"""matplotlib の共通スタイル

カテゴリ色は固定順で割り当て、循環させない（4色を超える場合は「その他」に畳む）
"""
from __future__ import annotations

import glob
import unicodedata
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MUTED = "#a9a8a2"
SEQ_BLUE = ["#d6e6f8", "#a3c7ef", "#6aa3e3", "#2a78d6", "#1d5aa5", "#123d72"]

# macOS のファイル名は NFD のため、glob 後に NFC 正規化して判定する
FONT_CANDIDATES = [
    ("/opt/X11/share/system_fonts/*.ttc", "角ゴシック W4"),
    ("/System/Library/Fonts/*.ttc", "ヒラギノ角ゴシック W4"),
    ("/usr/share/fonts/opentype/noto/*.ttc", "NotoSansCJK-Regular"),
]


def setup() -> None:
    family = None
    for g, key in FONT_CANDIDATES:
        for f in glob.glob(g):
            if key not in unicodedata.normalize("NFC", f):
                continue
            font_manager.fontManager.addfont(f)
            family = font_manager.FontProperties(fname=f).get_name()
            break
        if family:
            break
    plt.rcParams.update({
        "font.family": family or "sans-serif",
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": TEXT_2, "xtick.color": TEXT_2, "ytick.color": TEXT_2,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "axes.titlesize": 12,
        "axes.titlecolor": TEXT, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "lines.linewidth": 2, "figure.dpi": 110, "savefig.dpi": 140, "font.size": 9.5,
        "axes.prop_cycle": matplotlib.cycler(color=SERIES),
    })


def save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def compact_dates(ax, index) -> None:
    """期間が60日未満のとき、日付の目盛りを簡潔な表記にする（重なり防止）"""
    import matplotlib.dates as mdates
    if len(index) and (index.max() - index.min()).days < 60:
        loc = mdates.AutoDateLocator(maxticks=6)
        ax.xaxis.set_major_locator(loc)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
