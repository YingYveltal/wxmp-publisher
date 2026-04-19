# 开发指南

给后续接手开发新主题、新板块、调试问题的人用。

## 目录结构

```
wxmp-publisher/
├── README.md                       # 项目总览
├── INSTALL.md                      # 安装步骤
├── DEVELOPMENT.md                  # 本文档
├── CHANGELOG.md
├── LICENSE
└── skills/
    ├── md2wechat/                  # 渲染 skill
    │   ├── SKILL.md                # agent 操作手册
    │   ├── scripts/
    │   │   ├── render.py           # md → HTML 主程序
    │   │   └── img.py              # 本地图 → base64
    │   ├── themes/
    │   │   └── edwards/            # 主题
    │   │       ├── manifest.json   # 主题参数（颜色/字号/内边距/inline 样式）
    │   │       ├── body/default.html.j2
    │   │       ├── title/fallback.html.j2
    │   │       ├── quote/default.html.j2
    │   │       ├── divider/default.html.j2
    │   │       └── caption/default.html.j2
    │   └── examples/
    │       └── edwards-sample.md   # 完整示例（agent 学习材料）
    │
    └── text2md/                    # 策划 skill
        ├── SKILL.md
        └── scripts/
            └── plan.py             # scaffold + fill 两个子命令
```

## 加新主题（最常见的扩展）

假设要做一个商业财经主题 `business`：

### Step 1: 复制 edwards 当起点

```bash
cd skills/md2wechat/themes
cp -r edwards business
```

### Step 2: 改 `business/manifest.json`

关键字段：

```json
{
  "name": "business",
  "version": "1.0.0",
  "description": "商业财经主题：深蓝主色 + 衬线字体 + 紧凑行高",
  "defaults": {
    "title_h1": "fallback",
    "title_h2": "fallback",
    "title_h3": "fallback",
    "quote": "default",
    "divider": "default",
    "caption": "default",
    "body": "default"
  },
  "title_image": { ... },           // 章节标题图样式
  "image": { ... },                 // 普通图样式
  "list": { ... },                  // ul/ol 样式
  "inline": {                       // 行内样式
    "strong_style": "...",
    "mark_style": "...",            // ==高亮== 红字加粗
    "em_style": "...",
    "code_style": "...",
    "link_style": "..."
  },
  "code_block_style": "...",
  "interact": { ... },              // 互动板块
  "banner": { "max_width": "50%", "wrapper_style": "..." },
  "grid": { "gap": "8px", "aspect": 2.3, "title_style": "..." },
  "red_divider": { "color": "#1a3a8c" },
  "article_wrapper_style": "font-size: 14px; ..."   // ★ 全文基础样式都在这
}
```

**最重要的字段是 `article_wrapper_style`**——基础字号/字色/行高/字间距/内边距/对齐都在这里设。子节点继承这套，所以 body 模板里只需要设 margin 不需要重复字号/颜色。

### Step 3: 改各 `.html.j2` 模板片段

每个模板用 Jinja2 语法，传入 `{{ title }}` 或 `{{ content }}`。例：

```html
<!-- title/fallback.html.j2 -->
<section style="margin: 22px 0 10px; font-size: 17px; font-weight: bold; color: #1a3a8c;">
  {{ title }}
</section>
```

### Step 4: 视觉对比迭代（关键）

```bash
# 用 sample 渲染 + chrome headless 截图
python3 scripts/render.py path/to/sample.md --theme business --no-open
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --window-size=375,2000 --hide-scrollbars \
  --screenshot=/tmp/preview.png --virtual-time-budget=5000 \
  "file:///path/to/sample.html"
open /tmp/preview.png
```

如果是模仿某篇真实公众号文章：把原文也用 chrome headless 截图，并排对比，迭代调参数。

⚠ **千万不要光看 HTML 数值推断字号/字间距/行高**——公众号文章 99% 把基础样式写在最外层 wrapper section 上，子节点 inline style 都是空的（`margin:0;padding:0`），直接靠继承。如果你只统计 `<p>` 上的 font-size 频次，会误以为正文是 17px，实际是 14px。这是个真实的踩坑：[feedback_visual_extraction.md](#关键经验)。

### Step 5: 加到 examples

写一个用本主题完整跑通的 sample.md，放到 `skills/md2wechat/examples/business-sample.md`，让 agent 后续学习。

## 加新板块（不太常见）

如果要加新的 markdown directive（比如 `:::quote2`、`:::author-card`）：

### 修改 `scripts/render.py`

1. 在 `render_markdown()` 注册新 container：
   ```python
   for name in ("interact", "grid", "divider", "center", "banner", "quote2"):
       md.use(container_plugin, name=name)
   ```

2. 在 `render_container()` 里加分支：
   ```python
   if name == "quote2":
       cfg = manifest.get("quote2", {})
       wrapper_style = cfg.get("wrapper_style", "...")
       # 处理 inner_tokens 拼 HTML
       return f'<section style="{wrapper_style}">...</section>'
   ```

3. 在每个主题的 `manifest.json` 加 `quote2: {...}` 段。

4. 更新 `SKILL.md` 的板块速查表，让 agent 知道新写法。

5. 如果新板块属于"硬约束的版尾结构"，更新 `validate_footer()` 加检查。

## 加新主题的 inline 强调样式

比如想加"蓝字加粗"作为第三层强调：

1. `manifest.json` 加 `inline.highlight_style: "color: #015fc2; font-weight: bold;"`
2. `render.py` 的 `render_inline()` 加 markdown 语法识别（比如 `++text++`）：
   ```python
   parts_hl = re.split(r"\+\+([^+]+)\+\+", piece)
   ...
   ```
3. SKILL.md 加示例。

## 调试技巧

### 看渲染结果的 HTML 源码

```bash
# 去掉 base64 噪声看结构
python3 -c "
import re
t = open('out.html').read()
t = re.sub(r'data:image/[^;]+;base64,[^\"]{60,}', '[B64]', t)
print(t)
" | less
```

### 看版式与原版的差异

```bash
# Chrome headless 截图（原版 + 自己的输出），并排比较
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --window-size=375,3000 \
  --user-agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Version/16.0 Mobile/15E148 Safari/604.1" \
  --screenshot=/tmp/orig.png \
  --virtual-time-budget=10000 \
  'https://mp.weixin.qq.com/s/<token>'
```

### 看某段 markdown 渲染后是什么

```python
from markdown_it import MarkdownIt
md = MarkdownIt("commonmark", {"breaks": False, "html": True})
tokens = md.parse("== 红字 == 测试")
for t in tokens:
    print(t.type, repr(t.content), t.children)
```

## 关键经验（踩过的坑）

### 1. 视觉版式提取必须截图对比

公众号文章把基础样式写在最外层 wrapper section 上，子节点 inline style 都是空的。**纯统计 HTML 数值会被骗**——必须用 chrome headless 截图视觉对比迭代。第一版 `edwards` 主题正文字号设了 17px，因为我读到的是公众号默认值；实际 wrapper 上设的是 14px，子节点继承。视觉一对比立刻发现。

### 2. 公众号编辑器对 `img` 的 `max-width:%` 会过滤/覆盖

```html
<!-- ✗ 不行：粘贴后变 100% 撑满 -->
<img style="max-width: 50%; ...">

<!-- ✓ 必须这样：外层 section 限宽 + img 100% -->
<section style="display:inline-block; width:50%;">
  <img style="width:100%; height:auto;">
</section>
```

`banner` 板块就是为了这个原因设计成嵌套结构。任何"半屏图"类需求按这个模式做。

### 3. 用户不能 Ctrl+A 复制——必须用按钮

Ctrl+A 选中范围会包含 `.paper` / body 等预览容器，公众号过滤后样式错乱。`md2wechat` 输出的 HTML 内置了一个绿色的"📋 复制到公众号"按钮，用 `navigator.clipboard.write([ClipboardItem('text/html')])` 只选中 article wrapper section（纯净的、含正文 inline style 的那层）。

如果你做新板块，不需要管这个按钮——它在 `render.py` 的 main 里统一注入，与板块解耦。

### 4. 中文公众号文案规避 AI 痕迹

写中文稿子时严格遵守：
- **中文与英文/数字之间不加空格**：`1米93`，不是 `1 米 93`
- **用中文标点**：`""，。！？：`，不用英文 `"",.!?:`
- **段落开头不空两格**

这些是 AI 生成的常见标志，会被一眼识破。`text2md/SKILL.md` 里有完整规则，agent 写稿时自动遵守。

### 5. 微信公众号粘贴后图片要重新上传

base64 内嵌的图片粘贴到后台是临时显示，**发布前要点击图片"重新上传"或后台会自动转存到 mmbiz.qpic.cn**。否则发布出去图片可能失效。

### 6. 公众号必须 `<section>`，不能 `<div>` / class / `<style>` 块

`md2wechat` 输出严格遵守这条：所有容器都用 `<section>`，所有样式都 inline，没有 `<style>` 标签也没有 class。改新板块时也要保持。

## 为什么是两个 skill 而不是一个

[Hermes Agent](https://hermes-agent.nousresearch.com/docs/skills/) 倡导**原子能力 + 渐进式信息披露**——每个 skill 解决一个明确问题，agent 按需加载。

- `text2md` = 策划层（含 LLM 决策：标关键词、决定配图位置、跟用户分工）
- `md2wechat` = 渲染层（确定性脚本：markdown → HTML）

两者职责完全不同。用户已经有现成 markdown 时直接调 `md2wechat`，不需要加载 `text2md`。两个 skill 通过文件系统解耦：`text2md` 输出 `final.md`，`md2wechat` 消费 `final.md`，没有任何 API 耦合。

## 给 contributor 的 PR checklist

- [ ] 改主题：跑 chrome headless 截图，对比原版/旧版，确认视觉对齐
- [ ] 改板块：更新 SKILL.md 的板块速查表 + 例子；如果是版尾必有的，更新 `validate_footer()`
- [ ] 加依赖：写到 INSTALL.md 第 4 步
- [ ] CHANGELOG 加一条
- [ ] sample.md 跑通（端到端：scaffold → fill → render → 浏览器看效果）
