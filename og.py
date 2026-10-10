"""社交分享图：为每篇文章生成一张 1200×630 的 PNG。

字体直接复用构建产物的子集，和站点排版一致：
Syne 画品牌、Open Runde 画拉丁、霞鹜文楷画中文。
"""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import woff2
from PIL import Image, ImageDraw, ImageFont

from models import Post
from util import CACHE, log

WIDTH, HEIGHT = 1200, 630
PAD = 80
BG = (247, 247, 245)
FG = (26, 26, 24)
MUTED = (111, 109, 103)
ACCENT = (224, 54, 28)
CJK_START = 0x2E80


def _decompress(src: Path, name: str) -> Path:
    """把子集 woff2 解成 TTF（Pillow 只吃 TTF/OTF）。"""
    dest = CACHE / "og" / f"{name}.ttf"
    if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
        dest.parent.mkdir(parents=True, exist_ok=True)
        woff2.decompress(str(src), str(dest))
    return dest


def _pick(char: str, latin: ImageFont.FreeTypeFont, cjk: ImageFont.FreeTypeFont) -> ImageFont.FreeTypeFont:
    return cjk if ord(char) >= CJK_START else latin


def _measure(draw: ImageDraw.ImageDraw, text: str, latin, cjk) -> float:
    return sum(draw.textlength(char, font=_pick(char, latin, cjk)) for char in text)


def _wrap(draw: ImageDraw.ImageDraw, text: str, latin, cjk, max_width: float) -> list[str]:
    lines: list[str] = []
    line = ""
    for char in text:
        if _measure(draw, line + char, latin, cjk) <= max_width:
            line += char
        else:
            lines.append(line)
            line = char
    if line:
        lines.append(line)
    return lines


def _draw(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, latin, cjk, fill) -> float:
    """逐字选字体绘制（中英混排），返回结束位置。"""
    for char in text:
        font = _pick(char, latin, cjk)
        draw.text((x, y), char, font=font, fill=fill)
        x += draw.textlength(char, font=font)
    return x


def build(posts: list[Post], out_dir: Path, cfg: dict) -> None:
    fonts_dir = out_dir / "static" / "fonts"
    sources = {
        "syne": fonts_dir / "syne-latin-700-normal.woff2",
        "latin": fonts_dir / "open-runde-latin-400-normal.woff2",
        "cjk": fonts_dir / "lxgwwenkai-screen.woff2",
    }
    if not all(path.exists() for path in sources.values()):
        log("  ! 跳过分享图: 字体未就绪")
        return
    ttf = {name: _decompress(path, name) for name, path in sources.items()}

    brand = ImageFont.truetype(str(ttf["syne"]), 34)
    tagline = ImageFont.truetype(str(ttf["latin"]), 22)
    tagline_cjk = ImageFont.truetype(str(ttf["cjk"]), 22)
    title = ImageFont.truetype(str(ttf["latin"]), 60)
    title_cjk = ImageFont.truetype(str(ttf["cjk"]), 60)
    meta = ImageFont.truetype(str(ttf["latin"]), 24)
    meta_cjk = ImageFont.truetype(str(ttf["cjk"]), 24)

    og_dir = out_dir / "og"
    og_dir.mkdir(parents=True, exist_ok=True)

    for post in posts:
        image = Image.new("RGB", (WIDTH, HEIGHT), BG)
        draw = ImageDraw.Draw(image)

        end = _draw(draw, PAD, 70, cfg["author"], brand, brand, FG)
        draw.text((end, 70), ".", font=brand, fill=ACCENT)
        _draw(draw, PAD, 116, cfg["subtitle"], tagline, tagline_cjk, MUTED)

        lines = _wrap(draw, post.title, title, title_cjk, WIDTH - PAD * 2)[:3]
        line_h = 78
        block = len(lines) * line_h + 46
        y = 210 + (HEIGHT - 70 - 210 - block) // 2
        for line in lines:
            _draw(draw, PAD, y, line, title, title_cjk, FG)
            y += line_h

        caption = " · ".join([post.date, *(tag.name for tag in post.tags)])
        _draw(draw, PAD, y + 6, caption, meta, meta_cjk, MUTED)

        image.save(og_dir / f"{post.number}.png", optimize=True)

    log(f"  分享图: {len(posts)} 张")
