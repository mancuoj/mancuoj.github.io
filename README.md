# Mancouj

一个 GitHub Issues 驱动的极简个人博客。所有文章都是本仓库的 issue，构建脚本把它们渲染成静态站点发布到 GitHub Pages。

- 线上地址：<https://mancuoj.github.io>
- 写作方式：新建 issue 即发布，关闭 issue 即下线；issue 的 label 就是文章标签；置顶用 GitHub 自带的 pin。

## 本项目结构

```
config.json          # 站点配置：标题、作者、导航、评论、分页等
build.py             # 生成器：拉 issue → 渲染 Markdown → 输出静态站点
templates/           # Jinja2 模板：base / index / post / tags / 404
static/              # style.css、app.js
docs/                # 构建产物（已 gitignore，不提交）
requirements.txt
.github/workflows/build.yml
```

## 本地预览

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 用本地地址生成，方便预览（需要 token 走 GitHub 官方渲染 / 提高额度）
GH_TOKEN=$(gh auth token) .venv/bin/python build.py --base http://localhost:8137

# 起个静态服务
cd docs && python3 -m http.server 8137
```

然后打开 <http://localhost:8137/>。不带 `--base` 生成的就是正式链接。

## 设计说明

- 极简阅读向：系统字体、单栏窄版、克制的留白与细线分隔。
- 亮 / 暗两套主题，默认跟随系统，切换后记忆在 `localStorage`。
- 想换个人主色，改 `static/style.css` 里的 `--accent` 与 `--accent-soft` 即可。
- 评论走 [utterances](https://utteranc.es)，映射到对应的 issue。

## 依赖

生成器是纯 Python：`requests`、`Jinja2`、`markdown-it-py`（本地 Markdown 兜底）、`Pygments`。
CI 里优先调用 GitHub 官方 Markdown API 渲染，保证和 issue 里所见一致；API 不可用时自动回退本地渲染。
