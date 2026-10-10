"""字体管线：下载 → 按页面用到的字裁剪 → 自托管。

缓存放在 .cache/：fonts/ 存原始下载，subset/ 按正文哈希存裁剪结果。
"""

from __future__ import annotations

import hashlib
import html
import shutil
import subprocess
import sys
from pathlib import Path

import requests

from util import CACHE, log

FONTDIR = CACHE / "fonts"
SUBSETDIR = CACHE / "subset"
CJK_TTF = FONTDIR / "LXGWWenKaiScreen.ttf"

# (字体名, 字重) -> 下载地址（拉丁字体本身已是子集，仍会再裁一次）
LATIN_FONTS = {
    ("Open Runde", 400): "https://cdn.jsdelivr.net/npm/@fontsource/open-runde/files/open-runde-latin-400-normal.woff2",
    ("Open Runde", 500): "https://cdn.jsdelivr.net/npm/@fontsource/open-runde/files/open-runde-latin-500-normal.woff2",
    ("Syne", 700): "https://cdn.jsdelivr.net/npm/@fontsource/syne/files/syne-latin-700-normal.woff2",
}
CJK_FAMILY = "LXGW WenKai Screen"
CJK_TTF_URL = "https://github.com/lxgw/LxgwWenKai-Screen/releases/download/v1.522/LXGWWenKaiScreen.ttf"
CJK_CDN_CSS = "https://cn-font.claude-code-best.win/packages/lywkpmydb/dist/LXGWWenKaiScreen/result.css"
# 固定补充字符：数字、标点、箭头、置顶标记等
EXTRA_CHARS = " 0123456789.,:;·—…←→✳()[]%+-/@"


class Fonts:
    """构建自托管字体：下载、裁剪、写 fonts.css。"""

    def __init__(self, out_dir: Path, session: requests.Session):
        self.out = out_dir
        self.session = session

    def _download(self, url: str, dest: Path) -> bool:
        if dest.exists() and dest.stat().st_size > 0:
            return True
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            resp = self.session.get(url, timeout=180)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return True
        except requests.RequestException as exc:
            log(f"  ! 字体下载失败 {url}: {exc}")
            return False

    @staticmethod
    def _subset(src: Path, dest: Path, text: str) -> bool:
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fontTools.subset",
                    str(src),
                    f"--text={text}",
                    "--flavor=woff2",
                    f"--output-file={dest}",
                    "--layout-features=*",
                    "--no-hinting",
                    "--name-IDs=*",
                ],
                check=True,
                capture_output=True,
            )
            return dest.exists() and dest.stat().st_size > 0
        except (subprocess.CalledProcessError, OSError) as exc:
            detail = exc.stderr.decode("utf-8", "ignore")[:200] if hasattr(exc, "stderr") and exc.stderr else exc
            log(f"  ! 字体裁剪失败 {src.name}: {detail}")
            return False

    def _subset_cached(self, src: Path, dest: Path, text: str) -> bool:
        """按正文哈希缓存裁剪结果，正文没变就复用。"""
        key = hashlib.sha1(text.encode()).hexdigest()[:16]
        cached = SUBSETDIR / key / dest.name
        if cached.exists() and cached.stat().st_size > 0:
            shutil.copyfile(cached, dest)
            return True
        if not self._subset(src, dest, text):
            return False
        cached.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dest, cached)
        return True

    def _collect_text(self) -> str:
        """收集所有生成页面里出现过的字符（含属性值）。

        必须在页面生成之后调用：没有 HTML 就没有字形集合。
        """
        pages = list(self.out.rglob("*.html"))
        assert pages, "字体裁剪要在页面生成之后运行：没有找到任何 HTML"
        chars: set[str] = set()
        for path in pages:
            chars.update(html.unescape(path.read_text(encoding="utf-8", errors="ignore")))
        chars.update(EXTRA_CHARS)
        return "".join(sorted(c for c in chars if c == " " or c.isprintable()))

    def _prune_subset(self, text: str) -> None:
        """只保留当前内容的裁剪结果，避免缓存目录无限增长。"""
        keep = hashlib.sha1(text.encode()).hexdigest()[:16]
        for path in SUBSETDIR.glob("*"):
            if path.is_dir() and path.name != keep:
                shutil.rmtree(path, ignore_errors=True)

    def build(self) -> None:
        text = self._collect_text()
        fontdir = self.out / "static" / "fonts"
        fontdir.mkdir(parents=True, exist_ok=True)
        rules: list[str] = []
        total = 0
        for (family, weight), url in LATIN_FONTS.items():
            src = FONTDIR / url.rsplit("/", 1)[-1]
            local = fontdir / src.name
            if self._download(url, src) and self._subset_cached(src, local, text):
                rules.append(
                    f'@font-face{{font-family:"{family}";font-style:normal;font-weight:{weight};'
                    f'font-display:swap;src:url("fonts/{local.name}") format("woff2")}}'
                )
                total += local.stat().st_size
            else:
                rules.append(
                    f'@font-face{{font-family:"{family}";font-style:normal;font-weight:{weight};'
                    f'font-display:swap;src:url("{url}") format("woff2")}}'
                )
        ttf = CJK_TTF
        local = fontdir / "lxgwwenkai-screen.woff2"
        if self._download(CJK_TTF_URL, ttf) and self._subset_cached(ttf, local, text):
            rules.append(
                f'@font-face{{font-family:"{CJK_FAMILY}";font-style:normal;font-weight:400;'
                f'font-display:swap;src:url("fonts/{local.name}") format("woff2")}}'
            )
            total += local.stat().st_size
            cjk = f"{local.stat().st_size / 1024:.0f} KB (裁剪自 {len(text)} 字)"
        else:
            rules.insert(0, f'@import url("{CJK_CDN_CSS}");')
            cjk = "CDN 回退"
        (self.out / "static" / "fonts.css").write_text("\n".join(rules) + "\n", encoding="utf-8")
        self._prune_subset(text)
        log(f"  字体: {cjk}, 自托管合计 {total / 1024:.0f} KB")
