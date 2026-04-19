---
name: md2wechat
description: 把 markdown + 本地图片排版生成可一键粘贴到微信公众号后台的 HTML，全 inline style + base64 内嵌图。内置 edwards 主题（仿全明星街球派对风格），支持 12 个板块和 frontmatter 临时覆盖参数
version: 1.0.0
platforms: [macos, linux]
metadata:
  hermes:
    tags: [wechat, publishing, markdown, html, mp]
    category: content
    requires_toolsets: [terminal]
---

# md2wechat

把一篇 markdown 稿子（含本地图片）排版成可以**一键粘贴**到微信公众号后台的 HTML 文件。

## When to Use

- 用户提供 markdown 稿子或纯文字稿，要求"排版好发到公众号"
- 用户给一堆图片素材 + 文字大纲，让你帮他拼出完整公众号文章

## Workflow（agent 怎么用）

```
1. 收用户素材：文字稿 + 本地图片路径
2. 按"板块速查表"拼装 markdown，写到一个 .md 文件
3. 调 python3 scripts/render.py /path/to/article.md --theme edwards
4. 输出 article.html，自动用浏览器打开
5. 告诉用户：在浏览器里 Ctrl+A → Ctrl+C，到 mp 后台 Ctrl+V
```

**重要**：写中文稿子时严格遵守：
- 中文与英文/数字之间**不加空格**（`1米93`，不是 `1 米 93`）
- 用**中文标点**（`，。""：！？`），不用英文标点
- 段落开头不空两格

这些是 AI 生成的常见痕迹，会被一眼识破。

## 硬约束：版尾结构必须完整

**只要文章用了 `:::interact`（互动板块），后续就必须依次出现以下板块**，缺一项 render.py 直接报错阻断（允许改文案和图片，不允许缺失结构）：

```
1. :::interact:::          # 互动板块（红字+黑字混合）
2. :::banner:::            # 装饰小标识图（如"球场热闻"）
3. :::grid:::              # 2x2 推文卡（4 张带链接图）
4. :::divider:::           # 红色分割线
5. ![](引导动图1)          # 第 1 个引导动图（如"点亮星标"，不带链接）
6. ![](引导动图2)          # 第 2 个引导动图（如活动 banner，不带链接）
```

**为什么硬约束**：原版公众号每篇文章的版尾都是这套完整结构，缺一块就会显得文章"没排版完"。agent 拼装时容易省略后面几个，所以 render.py 强制检查。

**怎么写**：参考 `examples/edwards-sample.md` 的尾部 30 行（从第一个 `::: interact` 到文末），把图片路径和文案换成你这篇文章的对应素材即可。

**短稿例外**：如果整篇文章不需要互动板块（比如纯新闻速递），不写 `:::interact`，验证就跳过——但这种情况版尾通常只有 1-2 张引导动图。

## 12 个板块速查（markdown 写法）

| 板块 | 写法 | 渲染 |
|---|---|---|
| **版头 banner** | `[![alt](banner.png)](https://url)` 单独成段 | 带链接的居中图 |
| **章节小标题图** | `# ![alt](section.png)` | 居中大图（火焰篮球 banner 这种）|
| **装饰小 banner** | `:::banner\n![alt](xx.png)\n:::` | 居中小图（默认 50% 宽，比章节标题图小）|
| **正文段** | 直接写文字 | 14px 黑字 line-height 2 |
| **第一层强调** | `**xxx**` | 黑加粗 |
| **第二层强调** | `==xxx==` | 红字加粗 #ba0808 |
| **正文插图** | `![alt](path.png)` 单独成段 | 居中 100% 宽图 |
| **图注** | 图后紧跟 `*文字*` | 灰字居中小字 |
| **斜体** | `*xxx*` 不在图后 | 灰斜体（弱化）|
| **互动板块** | `:::interact\n... \n:::` | 多行居中文字（红字行用 `==xxx==`）|
| **2x2 推文卡** | `:::grid\n[![标题1](img1)](url1)\n[![标题2](img2)](url2)\n... \n:::` | 2x2 网格，图按 2.3:1 比例裁切 |
| **红色分割线** | `:::divider\n:::` | 红线 + 红色斜方块装饰 |
| **版尾 banner** | `[![alt](footer.gif)](url)` 单独成段 | 同版头 |

完整端到端示例：`examples/edwards-sample.md`

## Frontmatter 临时覆盖参数

每篇 markdown 顶部可以加 yaml frontmatter，覆盖主题的某些参数（不动主题文件）：

```markdown
---
theme: edwards
overrides:
  banner.max_width: "70%"      # 这一篇的小 banner 改 70% 宽
  grid.aspect: 1.5             # 这一篇推文卡用方一点的图
  article_wrapper_style: "font-size: 16px; padding: 0 24px; ..."  # 临时改基础字号
---

正文从这里开始...
```

支持的覆盖路径用点号写：`parent.child: value`。值可以是字符串/数字/布尔。

## 主题级参数（themes/edwards/manifest.json）

改主题文件 = 改整个主题，长期生效。常用字段：

```json
{
  "article_wrapper_style": "font-size: 14px; color: #212121; letter-spacing: 1px; line-height: 2; padding: 0 22px; text-align: justify; ...",
  "title_image": { "img_style": "max-width: 100%; ..." },
  "image": { "wrapper_style": "...", "img_style": "..." },
  "banner": { "max_width": "50%", "wrapper_style": "..." },
  "grid": { "gap": "8px", "aspect": 2.3, "title_style": "..." },
  "interact": { "wrapper_style": "...", "line_style": "..." },
  "red_divider": { "color": "#ba0808" },
  "inline": {
    "strong_style": "font-weight: bold; color: #222222;",
    "mark_style": "color: #ba0808; font-weight: bold;",
    "em_style": "color: #555555; font-style: italic;",
    "link_style": "color: #015fc2; text-decoration: none;"
  }
}
```

## CLI Reference

```bash
python3 scripts/render.py <md_path> [--theme NAME] [--output PATH] [--no-open]
```

参数：
- `md_path` (位置参数)：markdown 文件路径
- `--theme` (默认 `edwards`)：主题名；frontmatter 里 `theme:` 字段会覆盖此参数
- `--output` / `-o`：自定义输出 HTML 路径，默认与 md 同目录同名 `.html`
- `--no-open`：不自动用浏览器打开（CI 或纯生成场景）

## 输出特点

- 全 `<section>` + inline style，无 `<div>` / class / `<style>` 块（公众号编辑器要求）
- 本地图片 → base64 data URI 内嵌（离线 HTML 也能看；粘贴到公众号后台会自动转存到素材库）
- 移动端基础字号 14px，宽度按 iPhone 375 设计；预览容器 .paper 模拟手机宽
- 输出 HTML 右上角带"📋 复制到公众号"按钮，点击用 `navigator.clipboard.write([ClipboardItem('text/html')])` 把 article wrapper 写入剪贴板（保留 inline style），到 mp 后台 Cmd/Ctrl+V 粘贴即可。fallback 用 `execCommand('copy')` 兜底

## 已知限制

- 表格、脚注、任务列表暂未支持
- 嵌套引用只渲染外层样式
- 单图 base64 > 5MB 会 warning，建议用户先压缩
- 球星技能卡（橙边框 + GIF + 灰字小注）这种复合组件未实现，需要时手写 HTML 用 `:::center` 拼装

## 主题列表

- **edwards**：仿全明星街球派对风格，14px 黑字 + 1px 字间距 + line-height 2 + 22px 内边距，红字加粗强调，2x2 推文卡支持链接

新增主题：在 `themes/<name>/` 下放 `manifest.json` + 各 type 子目录的 `.html.j2` 模板片段。manifest 字段参考 edwards 的写法。
