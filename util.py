"""通用工具：路径、日志与文本处理。"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".cache"


def log(*args) -> None:
    print(*args, flush=True)


def slugify(text: str) -> str:
    """生成稳定的 URL 片段；中文标签直接保留。"""
    text = unicodedata.normalize("NFKC", str(text)).strip().lower()
    text = re.sub(r"[\s/\\]+", "-", text)
    text = re.sub(r"[^\w\u4e00-\u9fff.-]", "", text)
    return text or "tag"


def plain_excerpt(md_text: str, limit: int = 160) -> str:
    """从 Markdown 正文里取第一段纯文本做摘要。"""
    if not md_text:
        return ""
    text = re.sub(r"```.*?```", "", md_text, flags=re.S)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"[>*_~]", "", text)
    for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
        text = para
        break
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text
