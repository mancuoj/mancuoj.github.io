#!/usr/bin/env python3
"""极简 GitHub Issues 博客生成器.

用法:
    python build.py [--out docs] [--config config.json] [--base URL]

数据来源: GitHub Issues (open 状态, 排除 Pull Request)。
产物: 静态 HTML / RSS / sitemap / robots, 默认输出到 docs/。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import backup
import feeds
import og
from fonts import Fonts
from models import Post, Tag, group_by_year, tags_index
from util import CACHE, ROOT, log, plain_excerpt, slugify

API = "https://api.github.com"
TIMEOUT = 30
RETRIES = 3
# 用来探测 GitHub 渲染结果的固定文本；它的哈希作为缓存签名，渲染器一变缓存自动失效
PROBE_MD = "probe\n\n- a\n\n`b`"


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
    """优先用 GitHub API 渲染；整批一致，并按内容哈希缓存。

    同一构建里不会混用两种渲染器：只要有一篇 API 渲染失败，整批回退本地。
    """

    def __init__(self, session: requests.Session, repo: str, token: str | None):
        self.session = session
        self.repo = repo
        self.token = token
        self.local = _local_md()

    def _api(self, text: str) -> str:
        resp = self.session.post(
            f"{API}/markdown",
            json={"text": text, "mode": "gfm", "context": self.repo},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def _key(renderer: str, text: str) -> str:
        return hashlib.sha1(f"{renderer}\x00{text}".encode()).hexdigest()

    def _one(self, renderer: str, text: str) -> str:
        if not text:
            return ""
        cached = CACHE / "markdown" / f"{self._key(renderer, text)}.html"
        if cached.exists():
            return cached.read_text(encoding="utf-8")
        rendered = self._api(text) if renderer == "api" else self.local.render(text)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(rendered, encoding="utf-8")
        return rendered

    def _prune(self, renderer: str, texts: list[str]) -> None:
        """只保留本次用到的缓存，避免目录无限增长。"""
        keep = {f"{self._key(renderer, text)}.html" for text in texts if text}
        for path in (CACHE / "markdown").glob("*.html"):
            if path.name not in keep:
                path.unlink()

    def render_all(self, texts: list[str]) -> list[str]:
        try:
            signature = "api@" + hashlib.sha1(self._api(PROBE_MD).encode()).hexdigest()[:8]
            rendered = [self._one(signature, text) for text in texts]
        except requests.RequestException as exc:
            log(f"  ! GitHub markdown API 失败, 整批回退本地渲染: {exc}")
            signature = "local"
            rendered = [self._one(signature, text) for text in texts]
        self._prune(signature, texts)
        return rendered


# --------------------------------------------------------------------------- #
# GitHub
# --------------------------------------------------------------------------- #
class GitHub:
    def __init__(self, repo: str, token: str | None):
        self.repo = repo
        self.token = token
        self.session = requests.Session()
        retry = Retry(
            total=RETRIES,
            connect=RETRIES,
            read=RETRIES,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=None,
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
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

    def pinned_numbers(self) -> set[int]:
        """一次 GraphQL 取回所有置顶 issue 的编号（替代逐个 timeline 请求）。"""
        if not self.token:
            log("  ! 未提供 token, 跳过原生置顶检测")
            return set()
        owner, _, name = self.repo.partition("/")
        query = (
            "query($owner:String!,$name:String!){"
            "repository(owner:$owner,name:$name){pinnedIssues(first:100){nodes{issue{number}}}}}"
        )
        try:
            resp = self.session.post(
                f"{API}/graphql",
                json={"query": query, "variables": {"owner": owner, "name": name}},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            nodes = resp.json()["data"]["repository"]["pinnedIssues"]["nodes"]
            return {n["issue"]["number"] for n in nodes}
        except (requests.RequestException, KeyError, TypeError) as exc:
            log(f"  ! 获取置顶 issue 失败, 跳过: {exc}")
            return set()


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
        self.fonts = Fonts(out_dir, gh.session)
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
        self.env.globals["asset_ver"] = ""

    def render(self, template: str, **ctx) -> str:
        return self.env.get_template(template).render(**ctx)

    # -- 数据 --------------------------------------------------------------- #
    def collect(self) -> list[Post]:
        pinned_numbers = self.gh.pinned_numbers()
        issues = self.gh.issues()
        raws = [issue.get("body") or "" for issue in issues]
        rendered = self.md.render_all(raws)
        posts: list[Post] = []
        for issue, raw, body in zip(issues, raws, rendered, strict=True):
            names = [label["name"] for label in issue.get("labels", [])]
            created = self._local_time(issue["created_at"])
            posts.append(
                Post(
                    number=issue["number"],
                    title=issue["title"],
                    raw=raw,
                    body=body,
                    excerpt=plain_excerpt(raw),
                    created=created,
                    updated=self._local_time(issue["updated_at"]),
                    date=created.strftime("%Y-%m-%d"),
                    year=created.strftime("%Y"),
                    url=f"{self.base}/post/{issue['number']}.html",
                    source=issue["html_url"],
                    pinned=issue["number"] in pinned_numbers or (bool(self.pin_label) and self.pin_label in names),
                    tags=[Tag(name=n, slug=slugify(n)) for n in names if n not in self.exclude],
                )
            )
        posts.sort(key=lambda p: (p.pinned, p.created), reverse=True)
        return posts

    def _local_time(self, value: str) -> dt.datetime:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(self.tz)

    def _asset_ver(self, posts: list[Post]) -> str:
        """资源版本 = 静态文件 + 模板 + 配置 + 正文的内容哈希。

        内容不变时 URL 不变，浏览器缓存可复用。
        """
        digest = hashlib.sha1()
        sources = sorted((ROOT / "static").rglob("*")) + sorted((ROOT / "templates").rglob("*"))
        for path in sources:
            if path.is_file():
                digest.update(path.name.encode("utf-8"))
                digest.update(path.read_bytes())
        digest.update((ROOT / "config.json").read_bytes())
        for post in posts:
            digest.update(f"{post.number}\n{post.title}\n{post.body}\n".encode())
        return digest.hexdigest()[:8]

    # -- 页面 --------------------------------------------------------------- #
    def build_posts(self, posts: list[Post]) -> None:
        post_dir = self.out / "post"
        post_dir.mkdir(parents=True, exist_ok=True)
        for post in posts:
            html_out = self.render("post.html", post=post)
            (post_dir / f"{post.number}.html").write_text(html_out, encoding="utf-8")

    def build_index(self, posts: list[Post]) -> None:
        html_out = self.render("index.html", groups=group_by_year(posts))
        (self.out / "index.html").write_text(html_out, encoding="utf-8")

    def build_tags(self, posts: list[Post], tags: list[Tag]) -> None:
        html_out = self.render("tags.html", posts=posts, tags=tags)
        (self.out / "tags.html").write_text(html_out, encoding="utf-8")

    def build_404(self) -> None:
        html_out = self.render("404.html")
        (self.out / "404.html").write_text(html_out, encoding="utf-8")

    def copy_static(self) -> None:
        src = ROOT / "static"
        dst = self.out / "static"
        if dst.exists():
            shutil.rmtree(dst)
        if src.exists():
            shutil.copytree(src, dst)

    # -- 入口 --------------------------------------------------------------- #
    def run(self) -> None:
        log(f"→ 拉取 issues: {self.gh.repo}")
        posts = self.collect()
        log(f"  共 {len(posts)} 篇")
        tags = tags_index(posts)
        backup.write_backup(posts, ROOT / "backup")
        self.env.globals["asset_ver"] = self._asset_ver(posts)

        if self.out.exists():
            shutil.rmtree(self.out)
        self.out.mkdir(parents=True)

        self.build_posts(posts)
        self.build_index(posts)
        self.build_tags(posts, tags)
        self.build_404()
        feeds.build_rss(posts, self.cfg, self.base, self.out)
        feeds.build_sitemap(posts, self.cfg, self.base, self.out)
        feeds.build_robots(self.base, self.out)
        self.copy_static()
        self.fonts.build()
        og.build(posts, self.out, self.cfg["author"])
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
