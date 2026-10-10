"""站点文件：RSS 订阅、sitemap、robots。"""

from __future__ import annotations

import html
from pathlib import Path

from models import Post

RSS_TIME = "%a, %d %b %Y %H:%M:%S %z"
SITE_DATE = "%Y-%m-%d"


def build_rss(posts: list[Post], cfg: dict, base: str, out: Path) -> None:
    if not cfg.get("showRss", True):
        return
    items = []
    for p in posts:
        items.append(
            "\n".join(
                [
                    "    <item>",
                    f"      <title>{html.escape(p.title)}</title>",
                    f"      <link>{p.url}</link>",
                    f'      <guid isPermaLink="true">{p.url}</guid>',
                    f"      <pubDate>{p.created.strftime(RSS_TIME)}</pubDate>",
                    f"      <description><![CDATA[{p.excerpt}]]></description>",
                    "    </item>",
                ]
            )
        )
    last = posts[0].created.strftime(RSS_TIME) if posts else ""
    xml = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
            "  <channel>",
            f"    <title>{html.escape(cfg['title'])}</title>",
            f"    <link>{base}</link>",
            f"    <description>{html.escape(cfg['description'])}</description>",
            f"    <language>{cfg.get('lang', 'zh-CN')}</language>",
            f"    <lastBuildDate>{last}</lastBuildDate>",
            f'    <atom:link href="{base}/rss.xml" rel="self" type="application/rss+xml"/>',
            *items,
            "  </channel>",
            "</rss>",
            "",
        ]
    )
    (out / "rss.xml").write_text(xml, encoding="utf-8")


def build_sitemap(posts: list[Post], cfg: dict, base: str, out: Path) -> None:
    if not cfg.get("sitemap", True):
        return
    newest = max((p.updated for p in posts), default=None)
    newest = newest.strftime(SITE_DATE) if newest else ""
    urls = []
    for loc in (f"{base}/", f"{base}/tags.html"):
        mod = f"<lastmod>{newest}</lastmod>" if newest else ""
        urls.append(f"  <url><loc>{loc}</loc>{mod}</url>")
    for p in posts:
        urls.append(
            f"  <url><loc>{p.url}</loc><lastmod>{p.updated.strftime(SITE_DATE)}</lastmod></url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
    (out / "sitemap.xml").write_text(xml, encoding="utf-8")


def build_robots(base: str, out: Path) -> None:
    text = f"User-agent: *\nAllow: /\n\nSitemap: {base}/sitemap.xml\n"
    (out / "robots.txt").write_text(text, encoding="utf-8")
