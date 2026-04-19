# wxmp-publisher

> 让 [Hermes Agent](https://github.com/nousresearch/hermes-agent) 把一段纯文字稿排版成一键粘贴到微信公众号后台的精美 HTML

由两个串联的 skill 组成：

| Skill | 角色 | 输入 | 输出 |
|---|---|---|---|
| **`text2md`** | 策划层（含 LLM 决策）| 纯文字稿 `.txt` | `draft.md` + `images.json` 配图清单 |
| **`md2wechat`** | 渲染层（确定性脚本）| 标准 markdown | 含一键复制按钮的 HTML |

```
你的文字稿
   ↓ /text2md new "<文章主题>"
~/wxmp-articles/2026-04-20-<主题>/        ← 文章工作区（自动创建）
├── source.txt                            ← 你/agent 写入文字稿
├── images/                               ← 图素材
└── ...

   ↓ /text2md scaffold <workspace>/source.txt
draft.md（含 ![[IMG:id]] 占位符）+ images.json（配图清单）
   ↓ agent 跟你对话分工：哪些图你准备 / 哪些 agent 准备
   ↓ 各自把图存到 <workspace>/images/，回填 images.json 的 file/link_url
   ↓ /text2md fill <workspace>
final.md（标准 markdown）
   ↓ /md2wechat
final.html（含「📋 复制到公众号」按钮）
   ↓ 点按钮 → 公众号后台 Cmd/Ctrl+V
完成 ✅
```

**工作区根目录**默认 `~/wxmp-articles/`（首次自动创建），可通过环境变量 `WXMP_ARTICLES_DIR` 覆盖。每篇文章一个独立目录，所有素材集中、易归档。

## 当前内置主题

- **`edwards`**：仿"全明星街球派对"风格，14px 黑字 + 1px 字间距 + line-height 2 + 22px 内边距，红字加粗强调，2x2 推文卡支持链接。

新主题怎么加？看 [DEVELOPMENT.md](DEVELOPMENT.md)。

## 安装

详见 [INSTALL.md](INSTALL.md)。一句话版：

```bash
git clone https://github.com/<your>/wxmp-publisher.git
mkdir -p ~/.hermes/skills
cp -r wxmp-publisher/skills/* ~/.hermes/skills/
pip3 install --user markdown-it-py jinja2 mdit-py-plugins requests beautifulsoup4 lxml
```

## 12 个板块速查

`md2wechat` 支持 12 个板块，agent 用 markdown 拼装：

| # | 板块 | 写法 | 渲染 |
|---|---|---|---|
| 1 | 版头 banner（带链接） | `[![alt](banner.png)](url)` 单独成段 | 居中带链接图 |
| 2 | 章节小标题图 | `# ![alt](section.png)` | 居中大图（火焰篮球 banner 这种）|
| 3 | 装饰小 banner | `:::banner\n![alt](xx.png)\n:::` | 居中小图（默认 50% 宽）|
| 4 | 正文段 | 直接写文字 | 14px 黑字 line-height 2 |
| 5 | 第一层强调 | `**xxx**` | 黑加粗 |
| 6 | 第二层强调 | `==xxx==` | 红字加粗 #ba0808 |
| 7 | 正文插图 | `![alt](path.png)` 单独成段 | 居中 100% 宽图 |
| 8 | 图注 | 图后紧跟一行 `*文字*` | 灰字居中小字 |
| 9 | 斜体（弱化） | `*xxx*` 不在图后 | 灰斜体 |
| 10 | 互动板块 | `:::interact\n... \n:::` | 多行居中文字（红字行用 `==xxx==`）|
| 11 | 2x2 推文卡 | `:::grid\n[![标题1](img1)](url1)\n... \n:::` | 2x2 网格，图按 2.3:1 cover 裁切 |
| 12 | 红色分割线 | `:::divider\n:::` | 红线 + 红色斜方块装饰 |

末尾还有两张引导动图（无链接）：直接 `![alt](gif.gif)` 单独成段。

## 硬约束：版尾结构必须完整

只要文章用了 `:::interact`，后续必须依次出现：

```
1. :::interact:::
2. :::banner:::      # 球场热闻这种小标识
3. :::grid:::        # 2x2 推文卡
4. :::divider:::     # 红色分割线
5. ![](引导动图1)    # 不带链接
6. ![](引导动图2)    # 不带链接
```

缺一项 `md2wechat/scripts/render.py` 直接 `SystemExit` 阻断，列出缺失项。

## 使用示例

```bash
# 阶段 0：创建工作区（自动检查/创建 ~/wxmp-articles/）
python3 ~/.hermes/skills/text2md/scripts/plan.py new "edwards-蚁人超越加内特"
# → 输出工作区路径，如 ~/wxmp-articles/2026-04-20-edwards-蚁人超越加内特/

# 阶段 1：把稿子写入工作区的 source.txt（用编辑器或 Write 工具）

# 阶段 2：从文字稿生成骨架
python3 ~/.hermes/skills/text2md/scripts/plan.py scaffold <workspace>/source.txt

# 阶段 3：agent 读完文字稿后，自己在 draft.md 加 inline 占位符 + 给关键词加 ==红字== / **粗体**
# 阶段 4：agent 跟用户对话分工，把每张图的 owner / file / link_url 写到 images.json
# 阶段 5：填充
python3 ~/.hermes/skills/text2md/scripts/plan.py fill <workspace>

# 阶段 6：渲染
python3 ~/.hermes/skills/md2wechat/scripts/render.py <workspace>/final.md
# → 浏览器自动打开 final.html，点右上角「📋 复制到公众号」即可
```

## 文档

- **[INSTALL.md](INSTALL.md)** — 安装步骤、依赖、常见问题
- **[DEVELOPMENT.md](DEVELOPMENT.md)** — 新加主题、新加板块、调试方法、踩过的坑
- **[CHANGELOG.md](CHANGELOG.md)** — 版本变化
- **`skills/md2wechat/SKILL.md`** — md2wechat 完整手册
- **`skills/text2md/SKILL.md`** — text2md 完整手册

## License

MIT
