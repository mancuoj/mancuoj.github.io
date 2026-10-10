"""内容备份：把每篇 issue 的正文导出到仓库的 backup/ 目录。

issues 是内容的唯一来源，这里留一份仓库内的副本，便于恢复与追溯。
"""

from __future__ import annotations

import json
from pathlib import Path

from models import Post
from util import slugify


def _front_matter(post: Post) -> str:
    tags = json.dumps([tag.name for tag in post.tags], ensure_ascii=False)
    return (
        "---\n"
        f"number: {post.number}\n"
        f"title: {json.dumps(post.title, ensure_ascii=False)}\n"
        f"date: {json.dumps(post.date)}\n"
        f"updated: {json.dumps(post.updated.strftime('%Y-%m-%d'))}\n"
        f"tags: {tags}\n"
        f"source: {json.dumps(post.source)}\n"
        "---\n\n"
    )


def write_backup(posts: list[Post], out_dir: Path) -> None:
    """写出 backup/posts/<编号>-<标题>.md 与 backup/index.json。"""
    posts_dir = out_dir / "posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    for stale in posts_dir.glob("*.md"):
        stale.unlink()

    index = []
    for post in posts:
        filename = f"{post.number:04d}-{slugify(post.title)}.md"
        (posts_dir / filename).write_text(_front_matter(post) + post.raw.rstrip() + "\n", encoding="utf-8")
        index.append(
            {
                "number": post.number,
                "title": post.title,
                "date": post.date,
                "updated": post.updated.strftime("%Y-%m-%d"),
                "tags": [tag.name for tag in post.tags],
                "url": post.url,
                "source": post.source,
            }
        )

    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
