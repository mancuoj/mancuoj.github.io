# Mancouj

GitHub Issues 驱动的极简个人博客。每一篇 issue 就是一篇文章，构建脚本把它渲染成静态站点发布到 GitHub Pages。

**线上地址 · <https://mancuoj.github.io>**

## 特性

- **用 issue 写作**：新建 issue 即发布，关闭即下线；编辑 issue 自动重新构建
- **标签即分类**：issue 的 label 就是文章标签
- **置顶**：pin 该 issue，或给它加 `pin` 标签
- **极简阅读向**：单栏窄版、系统字体、克制的留白与细线分隔
- **亮 / 暗主题**：默认跟随系统，切换后记忆在本地
- **评论**：点击后才加载 utterances，映射到对应 issue
- **RSS · sitemap · 404 · 分页 · 标签页搜索**
- **零状态**：全量重建，构建产物不写回仓库，仓库里只有源码

## 怎么写一篇文章

1. 在本仓库新建一个 Issue，**标题**就是文章标题，**正文**用 Markdown 书写
2. 给它打上 label，作为文章标签
3. 想置顶：pin 这个 issue，或加一个 `pin` label
4. 保存后 GitHub Action 会自动重建并部署

> 关闭 issue 即从站点下线；删除 issue 则彻底移除。

评论走 [utterances](https://utteranc.es)，需要在仓库上安装一次它的 GitHub App。

## 目录结构

```
config.json                      # 站点配置
build.py                         # 生成器：拉 issue → 渲染 Markdown → 输出静态站点
templates/                       # Jinja2 模板
├─ base.html                     # 布局骨架（页头 / 页脚 / 主题脚本）
├─ index.html                    # 首页与分页列表
├─ post.html                     # 文章页
├─ tags.html                     # 标签页（过滤 + 搜索）
└─ 404.html
static/
├─ style.css                     # 全部样式，改 --accent 即可换主色
└─ app.js                        # 主题切换、评论懒加载、标签过滤
requirements.txt
.github/workflows/build.yml      # 构建 + 部署到 GitHub Pages
docs/                            # 构建产物（已 gitignore，不提交）
```

## 配置

全部在 `config.json`：

| 字段 | 说明 |
| --- | --- |
| `title` / `subtitle` / `description` | 站点标题、副标题、描述 |
| `author` | 作者名，显示在页脚 |
| `avatar` | 头像，同时作为 favicon |
| `repo` | issue 所在的仓库，`owner/name` |
| `homeUrl` | 站点地址，用于生成绝对链接 |
| `lang` | 页面语言，如 `zh-CN` |
| `timezone` | 时区偏移，如 `8` |
| `postsPerPage` | 首页每页文章数 |
| `excludeLabels` | 不作为标签展示的 label |
| `pinLabel` | 被视为置顶的 label 名 |
| `nav` | 顶部导航，`[{ "label": "...", "url": "..." }]` |
| `social` | 页脚链接，`[{ "label": "...", "url": "..." }]` |
| `footer` | 页脚附注，留空则不显示 |
| `showRss` / `sitemap` | 是否生成 `rss.xml` / `sitemap.xml` |
| `showComments` / `commentsRepo` | 是否启用评论，以及评论映射到哪个仓库 |

## 本地预览

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 生成成指向本地的链接，方便预览（带 token 会走 GitHub 官方渲染）
GH_TOKEN=$(gh auth token) .venv/bin/python build.py --base http://localhost:8137

# 起一个静态服务
cd docs && python3 -m http.server 8137
```

然后打开 <http://localhost:8137/>。不带 `--base` 生成的就是线上实际链接。

## 工作原理

```
GitHub Issues ──► build.py ──► docs/ ──► GitHub Pages
                    │
                    ├─ Markdown：优先调用 GitHub 官方 API（与 issue 里所见完全一致），
                    │            不可用时回退到本地 markdown-it 渲染
                    ├─ 抓取：标题、labels、创建时间、评论数、pin 状态
                    └─ 输出：HTML · rss.xml · sitemap.xml
```

- 构建由 `issues` 事件、`push`、每天定时（00:00 UTC+8）以及手动触发
- CI 里用 `GITHUB_TOKEN` 拉取 issue
- 产物直接作为 Pages artifact 部署，**不写回仓库**，因此没有自动提交噪音

## 设计

- **大字标识 + 小字正文**：`Syne` 排的 `mancuoj.` 作页面标识，其余文字收小，靠大小对比出质感
- **字体全部自托管、构建时裁剪**：
  - `Open Runde`（拉丁 UI）、`Syne`（标识）、`霞鹜文楷屏幕阅读版`（中文正文）
  - 构建时收集页面实际用到的字符，用 `fontTools` 裁剪成 woff2（中文通常 200KB 上下），产物在 `docs/static/fonts/`
  - 字体源缓存于 `.fontcache/`（CI 用 Actions cache）
- **亮 / 暗两套**，默认跟随系统，切换后记忆
- **换个人主色**：改 `static/style.css` 里的 `--accent`

## 依赖

生成器是纯 Python：`requests`、`Jinja2`、`markdown-it-py`（含 `mdit-py-plugins`）、`Pygments`，以及字体裁剪用的 `fonttools`、`brotli`。
