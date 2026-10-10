"""社交分享图：为每篇文章生成一张 1200×630 的 PNG。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from fonts import CJK_TTF
from models import Post
from util import log

WIDTH, HEIGHT = 1200, 630
PAD = 80
BG = (247, 247, 245)
FG = (26, 26, 24)
MUTED = (111, 109, 103)
ACCENT = (224, 54, 28)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """按像素宽度折行（中英文通用）。"""
    lines: list[str] = []
    line = ""
    for char in text:
        if draw.textlength(line + char, font=font) <= max_width:
            line += char
        else:
            lines.append(line)
            line = char
    if line:
        lines.append(line)
    return lines


def build(posts: list[Post], out_dir: Path, author: str) -> None:
    if not CJK_TTF.exists():
        log("  ! 跳过分享图: 字体未就绪")
        return
    og_dir = out_dir / "og"
    og_dir.mkdir(parents=True, exist_ok=True)
    brand = ImageFont.truetype(str(CJK_TTF), 30)
    title = ImageFont.truetype(str(CJK_TTF), 62)
    meta = ImageFont.truetype(str(CJK_TTF), 28)

    for post in posts:
        image = Image.new("RGB", (WIDTH, HEIGHT), BG)
        draw = ImageDraw.Draw(image)

        draw.text((PAD, 64), author, font=brand, fill=FG)
        width = draw.textlength(author, font=brand)
        draw.text((PAD + width, 64), ".", font=brand, fill=ACCENT)

        lines = _wrap(draw, post.title, title, WIDTH - PAD * 2)[:4]
        y = (HEIGHT - len(lines) * 78) // 2 + 16
        for line in lines:
            draw.text((PAD, y), line, font=title, fill=FG)
            y += 78

        caption = " · ".join([post.date, *(tag.name for tag in post.tags)])
        draw.text((PAD, HEIGHT - PAD - 20), caption, font=meta, fill=MUTED)

        image.save(og_dir / f"{post.number}.png", optimize=True)

    log(f"  分享图: {len(posts)} 张")
