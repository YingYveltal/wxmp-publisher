# 安装

## 1. 前置依赖

- macOS 或 Linux（Windows 未测试）
- Python 3.9+
- Chrome / Chromium（仅渲染验证用，可选）
- [Hermes Agent](https://github.com/nousresearch/hermes-agent)（如果还没装，看 hermes-agent 官方文档）

## 2. 克隆仓库

```bash
git clone https://github.com/<your>/wxmp-publisher.git
cd wxmp-publisher
```

## 3. 装到 Hermes skills 目录

Hermes 默认在 `~/.hermes/skills/` 下识别 skill。两种安装方式：

### 方式 A：复制（推荐生产用）

```bash
mkdir -p ~/.hermes/skills
cp -r skills/* ~/.hermes/skills/
```

升级时重新 `cp -r` 覆盖即可。

### 方式 B：符号链接（推荐开发用）

```bash
mkdir -p ~/.hermes/skills
ln -s "$(pwd)/skills/md2wechat" ~/.hermes/skills/md2wechat
ln -s "$(pwd)/skills/text2md"   ~/.hermes/skills/text2md
```

之后 git pull 立刻生效，方便迭代主题。

## 4. 装 Python 依赖

```bash
pip3 install --user \
  markdown-it-py \
  jinja2 \
  mdit-py-plugins \
  requests \
  beautifulsoup4 \
  lxml
```

如果用 `uv`/`poetry`：从上面包列表自取。

## 5. 验证安装

```bash
# 测 md2wechat
python3 ~/.hermes/skills/md2wechat/scripts/render.py \
  ~/.hermes/skills/md2wechat/examples/edwards-sample.md \
  --no-open
# 应输出 [ok] 已生成 ...edwards-sample.html

# 测 text2md
echo "测试稿" > /tmp/_test.txt
python3 ~/.hermes/skills/text2md/scripts/plan.py scaffold /tmp/_test.txt --out-dir /tmp/_out
ls /tmp/_out
# 应有 draft.md / images.json / images/
```

两个命令都跑通就装好了。

## 6. 常见问题

### Q: `ModuleNotFoundError: No module named 'markdown_it'`

A: 没装 Python 依赖，回到第 4 步。

### Q: `pip3 install` 装到哪了？我在 PATH 里找不到

A: `--user` 装到 `~/Library/Python/<version>/lib/python/site-packages/`（Mac）或 `~/.local/lib/python<version>/site-packages/`（Linux）。Python 脚本能 import 即可，不需要 PATH。

### Q: 渲染时报 `theme not found: ...`

A: 检查 `~/.hermes/skills/md2wechat/themes/` 目录是否存在 `edwards/` 子目录及其 `manifest.json`。可能是 cp 命令没复制完。

### Q: 浏览器里"📋 复制到公众号"按钮点了没反应

A: 打开浏览器 DevTools Console 看错误。常见原因：
- Chrome 在 `file://` 协议下默认允许 Clipboard API；Safari 可能拒绝 → 用 Chrome
- 公司/学校受限网络可能拦截 `navigator.clipboard` → 换网络试

按钮 fallback 用 `execCommand('copy')`，理论上 100% 兼容；如果仍失败，DevTools 里看具体报错告诉我。

### Q: 粘贴到公众号后台有个别样式丢了

A: 见 [DEVELOPMENT.md](DEVELOPMENT.md) 「公众号粘贴丢样式排查清单」。最常见的是 `img` 上的 `max-width:%`——这个项目已经规避了，但如果你自定义新板块要注意。

### Q: 怎么调主题颜色 / 字号 / 内边距？

A: 直接编辑 `~/.hermes/skills/md2wechat/themes/edwards/manifest.json`。

### Q: 怎么临时调整某一篇的参数（不动主题）？

A: markdown 顶部加 yaml frontmatter：
```markdown
---
theme: edwards
overrides:
  banner.max_width: "70%"
  grid.aspect: 1.5
---
正文...
```

### Q: hermes-agent 怎么"看到" skill？

A: hermes 启动时扫描 `~/.hermes/skills/`，每个目录是一个 skill，`SKILL.md` 的 frontmatter 是元数据。装好后用 `/text2md` 或 `/md2wechat` 命令调用。

### Q: 不用 hermes 行吗？

A: 行。两个 skill 的 `scripts/` 都是普通 Python 脚本，可以独立跑。SKILL.md 是给 LLM 看的操作手册，对人类也算文档。
