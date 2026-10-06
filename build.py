#!/usr/bin/env python3
"""极简 GitHub Issues 博客生成器.

用法:
    python build.py [--out docs] [--config config.json] [--base URL]

数据来源: GitHub Issues (open 状态, 排除 Pull Request)。
产物: 静态 HTML / RSS / sitemap, 默认输出到 docs/。
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from mdit_py_plugins.deflist import deflist_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

ROOT = Path(__file__).resolve().parent
API = "https://api.github.com"
TIMEOUT = 30

# --- 字体：构建时按用到的字裁剪后自托管 ------------------------------------- #
FONTCACHE = ROOT / ".fontcache"
# (font-family, weight) -> 下载地址（拉丁字体已是子集，仍会再裁一次）
LATIN_FONTS = {
    ("Open Runde", 400): "https://cdn.jsdelivr.net/npm/@fontsource/open-runde/files/open-runde-latin-400-normal.woff2",
    ("Open Runde", 500): "https://cdn.jsdelivr.net/npm/@fontsource/open-runde/files/open-runde-latin-500-normal.woff2",
    ("Syne", 700): "https://cdn.jsdelivr.net/npm/@fontsource/syne/files/syne-latin-700-normal.woff2",
}
CJK_FAMILY = "LXGW WenKai Screen"
CJK_TTF_URL = "https://github.com/lxgw/LxgwWenKai-Screen/releases/download/v1.522/LXGWWenKaiScreen.ttf"
CJK_CDN_CSS = "https://cn-font.claude-code-best.win/packages/lywkpmydb/dist/LXGWWenKaiScreen/result.css"


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def log(*args):
    print(*args, flush=True)


def slugify(text: str) -> str:
    """生成稳定的 URL 片段; 中文标签直接保留。"""
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


# --------------------------------------------------------------------------- #
# Markdown: 优先 GitHub API, 失败回退本地渲染
# --------------------------------------------------------------------------- #
def _highlight(code: str, lang: str, _attrs) -> str:
    try:
        lexer = get_lexer_by_name(lang or "text")
    except ClassNotFound:
        lexer = get_lexer_by_name("text")
    formatter = HtmlFormatter(nowrap=False, cssclass="highlight")
    return highlight(code, lexer, formatter)


def _local_md() -> MarkdownIt:
    md = MarkdownIt(
        "gfm-like",
        {"linkify": True, "highlight": _highlight, "typographer": False},
    )
    md.use(footnote_plugin).use(deflist_plugin).use(tasklists_plugin)
    return md


class Markdown:
    def __init__(self, session: requests.Session, repo: str, token: str | None):
        self.session = session
        self.repo = repo
        self.token = token
        self.local = _local_md()
        self.api_ok: bool | None = None

    def render(self, text: str) -> str:
        if not text:
            return ""
        if self.api_ok is not False:
            try:
                resp = self.session.post(
                    f"{API}/markdown",
                    json={"text": text, "mode": "gfm", "context": self.repo},
                    timeout=TIMEOUT,
                )
                resp.raise_for_status()
                self.api_ok = True
                return resp.text
            except requests.RequestException as exc:
                log(f"  ! GitHub markdown API 失败, 回退本地渲染: {exc}")
                self.api_ok = False
        return self.local.render(text)


# --------------------------------------------------------------------------- #
# GitHub
# --------------------------------------------------------------------------- #
class GitHub:
    def __init__(self, repo: str, token: str | None):
        self.repo = repo
        self.token = token
        self.session = requests.Session()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mancuoj-blog",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.session.headers.update(headers)

    def _get(self, url: str, **params):
        resp = self.session.get(url, params=params or None, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp

    def issues(self) -> list[dict]:
        out, page = [], 1
        while True:
            batch = self._get(
                f"{API}/repos/{self.repo}/issues",
                state="open",
                sort="created",
                direction="desc",
                per_page=100,
                page=page,
            ).json()
            if not batch:
                break
            out.extend(i for i in batch if "pull_request" not in i)
            if len(batch) < 100:
                break
            page += 1
        return out

    def is_pinned(self, number: int) -> bool:
        try:
            events = self._get(
                f"{API}/repos/{self.repo}/issues/{number}/timeline",
                per_page=100,
            ).json()
        except requests.RequestException:
            return False
        pinned = False
        for event in events:
            if event.get("event") == "pinned":
                pinned = True
            elif event.get("event") == "unpinned":
                pinned = False
        return pinned


# --------------------------------------------------------------------------- #
# 构建
# --------------------------------------------------------------------------- #
class Builder:
    def __init__(self, cfg: dict, gh: GitHub, out_dir: Path, base: str = ""):
        self.cfg = cfg
        self.gh = gh
        self.out = out_dir
        self.tz = dt.timezone(dt.timedelta(hours=cfg.get("timezone", 8)))
        self.base = (base or cfg["homeUrl"]).rstrip("/")
        self.md = Markdown(gh.session, gh.repo, gh.token)
        self.exclude = set(cfg.get("excludeLabels", []))
        self.pin_label = cfg.get("pinLabel")
        self.env = Environment(
            loader=FileSystemLoader(ROOT / "templates"),
            autoescape=select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.globals["cfg"] = cfg
        self.env.globals["base"] = self.base
        self.env.globals["asset_ver"] = str(int(dt.datetime.now().timestamp()))

    def render(self, template: str, **ctx) -> str:
        return self.env.get_template(template).render(**ctx)

    # -- 数据 --------------------------------------------------------------- #
    def collect(self) -> list[dict]:
        posts = []
        for issue in self.gh.issues():
            labels = issue.get("labels", [])
            names = [l["name"] for l in labels]
            pinned = self.gh.is_pinned(issue["number"])
            if self.pin_label and self.pin_label in names:
                pinned = True
            body = issue.get("body") or ""
            created = dt.datetime.fromisoformat(
                issue["created_at"].replace("Z", "+00:00")
            ).astimezone(self.tz)
            posts.append(
                {
                    "number": issue["number"],
                    "title": issue["title"],
                    "body": self.md.render(body),
                    "excerpt": plain_excerpt(body),
                    "created": created,
                    "date": created.strftime("%Y-%m-%d"),
                    "year": created.strftime("%Y"),
                    "url": f"{self.base}/post/{issue['number']}.html",
                    "source": issue["html_url"],
                    "pinned": pinned,
                    "tags": [
                        {"name": n, "slug": slugify(n)}
                        for n in names
                        if n not in self.exclude
                    ],
                }
            )
        posts.sort(key=lambda p: (p["pinned"], p["created"]), reverse=True)
        return posts

    def tags_index(self, posts: list[dict]) -> list[dict]:
        buckets: dict[str, dict] = {}
        for post in posts:
            for tag in post["tags"]:
                b = buckets.setdefault(
                    tag["slug"], {"name": tag["name"], "slug": tag["slug"], "count": 0}
                )
                b["count"] += 1
        return sorted(buckets.values(), key=lambda b: (-b["count"], b["name"]))

    # -- 页面 --------------------------------------------------------------- #
    def build_posts(self, posts: list[dict]) -> None:
        post_dir = self.out / "post"
        post_dir.mkdir(parents=True, exist_ok=True)
        for post in posts:
            html_out = self.render("post.html", post=post)
            (post_dir / f"{post['number']}.html").write_text(html_out, encoding="utf-8")

    @staticmethod
    def group_by_year(posts: list[dict]) -> list[dict]:
        groups: list[dict] = []
        for p in posts:
            if not groups or groups[-1]["year"] != p["year"]:
                groups.append({"year": p["year"], "posts": []})
            groups[-1]["posts"].append(p)
        return groups

    def build_index(self, posts: list[dict]) -> None:
        html_out = self.render("index.html", groups=self.group_by_year(posts))
        (self.out / "index.html").write_text(html_out, encoding="utf-8")

    def build_tags(self, posts: list[dict], tags: list[dict]) -> None:
        html_out = self.render("tags.html", posts=posts, tags=tags)
        (self.out / "tags.html").write_text(html_out, encoding="utf-8")

    def build_404(self) -> None:
        html_out = self.render("404.html")
        (self.out / "404.html").write_text(html_out, encoding="utf-8")

    def build_rss(self, posts: list[dict]) -> None:
        if not self.cfg.get("showRss", True):
            return

        def cdata(text: str) -> str:
            return f"<![CDATA[{text}]]>"

        items = []
        for p in posts:
            items.append(
                "\n".join(
                    [
                        "    <item>",
                        f"      <title>{html.escape(p['title'])}</title>",
                        f"      <link>{p['url']}</link>",
                        f"      <guid isPermaLink=\"true\">{p['url']}</guid>",
                        f"      <pubDate>{p['created'].strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate>",
                        f"      <description>{cdata(html.escape(p['excerpt']))}</description>",
                        "    </item>",
                    ]
                )
            )
        last = posts[0]["created"].strftime("%a, %d %b %Y %H:%M:%S %z") if posts else ""
        xml = "\n".join(
            [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
                "  <channel>",
                f"    <title>{html.escape(self.cfg['title'])}</title>",
                f"    <link>{self.base}</link>",
                f"    <description>{html.escape(self.cfg['description'])}</description>",
                f"    <language>{self.cfg.get('lang', 'zh-CN')}</language>",
                f"    <lastBuildDate>{last}</lastBuildDate>",
                f'    <atom:link href="{self.base}/rss.xml" rel="self" type="application/rss+xml"/>',
                *items,
                "  </channel>",
                "</rss>",
                "",
            ]
        )
        (self.out / "rss.xml").write_text(xml, encoding="utf-8")

    def build_sitemap(self, posts: list[dict]) -> None:
        if not self.cfg.get("sitemap", True):
            return
        urls = [f"{self.base}/", f"{self.base}/tags.html"]
        urls += [p["url"] for p in posts]
        body = "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}\n</urlset>\n"
        )
        (self.out / "sitemap.xml").write_text(xml, encoding="utf-8")

    def copy_static(self) -> None:
        src = ROOT / "static"
        dst = self.out / "static"
        if dst.exists():
            shutil.rmtree(dst)
        if src.exists():
            shutil.copytree(src, dst)
        # Pygments 代码高亮样式由 style.css 内联定义, 这里不额外生成。

    # -- 字体：下载 → 按用字裁剪 → 自托管 ----------------------------------- #
    def _download(self, url: str, dest: Path) -> bool:
        if dest.exists() and dest.stat().st_size > 0:
            return True
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            resp = self.gh.session.get(url, timeout=180)
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
                    sys.executable, "-m", "fontTools.subset", str(src),
                    f"--text={text}",
                    "--flavor=woff2",
                    f"--output-file={dest}",
                    "--layout-features=*",
                    "--no-hinting",
                    "--name-IDs=*",
                ],
                check=True, capture_output=True,
            )
            return dest.exists() and dest.stat().st_size > 0
        except (subprocess.CalledProcessError, OSError) as exc:
            detail = exc.stderr.decode("utf-8", "ignore")[:200] if hasattr(exc, "stderr") and exc.stderr else exc
            log(f"  ! 字体裁剪失败 {src.name}: {detail}")
            return False

    def _collect_text(self) -> str:
        chars: set[str] = set()
        for path in self.out.rglob("*.html"):
            raw = path.read_text(encoding="utf-8", errors="ignore")
            # 连同属性值 (placeholder / title / alt / content) 一并收集，避免漏字
            chars.update(html.unescape(raw))
        chars.update(" 0123456789.,:;·—…←→✳()[]%+-/@")
        return "".join(sorted(c for c in chars if c == " " or c.isprintable()))

    def build_fonts(self) -> None:
        text = self._collect_text()
        fontdir = self.out / "static" / "fonts"
        fontdir.mkdir(parents=True, exist_ok=True)
        rules: list[str] = []
        total = 0
        for (family, weight), url in LATIN_FONTS.items():
            src = FONTCACHE / url.rsplit("/", 1)[-1]
            local = fontdir / src.name
            if self._download(url, src) and self._subset(src, local, text):
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
        ttf = FONTCACHE / "LXGWWenKaiScreen.ttf"
        local = fontdir / "lxgwwenkai-screen.woff2"
        if self._download(CJK_TTF_URL, ttf) and self._subset(ttf, local, text):
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
        log(f"  字体: {cjk}, 自托管合计 {total / 1024:.0f} KB")

    # -- 入口 --------------------------------------------------------------- #
    def run(self) -> None:
        log(f"→ 拉取 issues: {self.gh.repo}")
        posts = self.collect()
        log(f"  共 {len(posts)} 篇")
        tags = self.tags_index(posts)

        if self.out.exists():
            shutil.rmtree(self.out)
        self.out.mkdir(parents=True)

        self.build_posts(posts)
        self.build_index(posts)
        self.build_tags(posts, tags)
        self.build_404()
        self.build_rss(posts)
        self.build_sitemap(posts)
        self.copy_static()
        self.build_fonts()
        try:
            shown = self.out.relative_to(ROOT)
        except ValueError:
            shown = self.out
        log(f"✓ 输出到 {shown}/")


def main() -> int:
    parser = argparse.ArgumentParser(description="GitHub Issues blog generator")
    parser.add_argument("--out", default="docs", help="输出目录 (默认 docs)")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--base", default="", help="覆盖链接前缀 (本地预览用)")
    args = parser.parse_args()

    cfg = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    gh = GitHub(cfg["repo"], token)
    Builder(cfg, gh, ROOT / args.out, base=args.base).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
