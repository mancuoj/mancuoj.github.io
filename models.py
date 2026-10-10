"""数据模型：文章、标签、年份分组。"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tag:
    name: str
    slug: str


@dataclass
class Post:
    number: int
    title: str
    raw: str  # issue 原始 Markdown（用于备份）
    body: str  # 渲染后的 HTML
    excerpt: str
    created: dt.datetime
    updated: dt.datetime
    date: str
    year: str
    url: str
    source: str
    pinned: bool
    tags: list[Tag] = field(default_factory=list)


@dataclass
class YearGroup:
    year: str
    posts: list[Post] = field(default_factory=list)


def tags_index(posts: list[Post]) -> list[Tag]:
    """全部标签，按出现次数降序（次数只用于排序，不出现在页面）。"""
    counts: dict[str, int] = {}
    names: dict[str, str] = {}
    for post in posts:
        for tag in post.tags:
            counts[tag.slug] = counts.get(tag.slug, 0) + 1
            names.setdefault(tag.slug, tag.name)
    order = sorted(counts, key=lambda slug: (-counts[slug], names[slug]))
    return [Tag(name=names[slug], slug=slug) for slug in order]


def group_by_year(posts: list[Post]) -> list[YearGroup]:
    """把已排好序的文章按年份切段。"""
    groups: list[YearGroup] = []
    for post in posts:
        if not groups or groups[-1].year != post.year:
            groups.append(YearGroup(year=post.year))
        groups[-1].posts.append(post)
    return groups
