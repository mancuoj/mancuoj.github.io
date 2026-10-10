"""纯函数与站点输出的单元测试。"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import feeds
from models import Post, Tag, group_by_year, tags_index
from util import plain_excerpt, slugify


def make_post(number: int, year: str = "2026", tags: list[Tag] | None = None) -> Post:
    return Post(
        number=number,
        title=f"文章 {number}",
        body="",
        excerpt="",
        created=dt.datetime(2024, 1, 1),
        updated=dt.datetime(2024, 1, 1),
        date="2024-01-01",
        year=year,
        url=f"https://example.com/post/{number}.html",
        source="",
        pinned=False,
        tags=tags or [],
    )


def test_slugify_keeps_chinese_and_lowercases() -> None:
    assert slugify("Hello World") == "hello-world"
    assert slugify("随笔 Notes") == "随笔-notes"
    assert slugify("a/b\\c") == "a-b-c"
    assert slugify("  ") == "tag"


def test_plain_excerpt_drops_markup() -> None:
    md = "这是**第一**段，带[链接](https://a.example)。\n\n第二段"
    assert plain_excerpt(md) == "这是第一段，带链接。"
    assert "code" not in plain_excerpt("前 `code` 后")


def test_plain_excerpt_truncates() -> None:
    out = plain_excerpt("字" * 200)
    assert out.endswith("…")
    assert len(out) == 161


def test_group_by_year_splits_consecutive_years() -> None:
    groups = group_by_year([make_post(1, "2026"), make_post(2, "2026"), make_post(3, "2025")])
    assert [g.year for g in groups] == ["2026", "2025"]
    assert [len(g.posts) for g in groups] == [2, 1]


def test_tags_index_sorted_by_count_then_name() -> None:
    posts = [
        make_post(1, tags=[Tag("b", "b"), Tag("a", "a")]),
        make_post(2, tags=[Tag("a", "a")]),
    ]
    assert [t.slug for t in tags_index(posts)] == ["a", "b"]


def test_rss_does_not_double_escape_description(tmp_path: Path) -> None:
    post = make_post(1)
    post.title = "A & B"
    post.excerpt = "x & y < z"
    feeds.build_rss([post], {"title": "T", "description": "D"}, "https://example.com", tmp_path)
    xml = (tmp_path / "rss.xml").read_text(encoding="utf-8")
    assert "A &amp; B" in xml
    assert "<![CDATA[x & y < z]]>" in xml
