# Changelog

## v1.2.0 (2026-04-20)

### 修复

修两个会导致**公众号后台保存失败**的真实问题：

- **图片大小**：`md2wechat/scripts/img.py` 把 5MB warning 改为**硬阻断**，超大图直接 SystemExit 报清晰错误。
  原因：粘贴到公众号编辑器的单图硬上限 5MB（PNG/JPG/GIF 都一样），超过会保存失败"载入失败、来源信息无法识别"。
  素材库支持 10MB 但**粘贴通道**只允许 5MB。

- **链接真实性**：`text2md/scripts/plan.py` 加强 `_is_valid_link` 检查，拒绝形如 `/s/AbCd1111111111111` 这种"格式像但 token 是测试值"的 URL（连续重复字符、连续递增字符、字符种类过少）。
  原因：公众号保存时校验图文链接指向的推文是否真实存在，假 URL 会报"请勿插入不合法的图文消息链接"。

- **fill 阶段图片大小预检**：图片在 fill 时就被检查（不用等到 render）。

### 文档

- `text2md/SKILL.md`、`INSTALL.md` 加入这两个问题的根因和解决方案
- 强调 agent 不能用任何"测试 URL"凑数，链接必须从用户处获取真实可访问的 mp 推文 URL

## v1.1.0 (2026-04-20)

### `text2md`

- **新增 `new` 子命令**：一键创建文章工作区 `~/wxmp-articles/<YYYY-MM-DD>-<slug>/`，含 source.txt 占位 + images/ 空目录 + .layout 标识文件
- **工作区合法性检查**：scaffold 和 fill 都强制检查 `.layout` 标识，不在合法工作区直接报错（防 agent 误操作）
- `scaffold` 的 `--out-dir` 改为可选，缺省 = source.txt 所在目录
- 工作区根目录可通过环境变量 `WXMP_ARTICLES_DIR` 覆盖（默认 `~/wxmp-articles/`）
- 首次运行自动创建根目录并打印友好提示

### 设计动机

之前的工作流让 agent 自己决定中间文件存哪，容易散落多处导致后续命令找不到。强制工作区结构 + 标识文件检查彻底解决这个问题。

## v1.0.0 (2026-04-20)

首个完整版本。

### `md2wechat`

- 12 个板块：版头/章节标题图/装饰小 banner/正文/加粗/红字加粗/正文插图/图注/斜体/互动/2x2 推文卡/红色分割线
- 内置主题 `edwards`（仿全明星街球派对风格）
- markdown frontmatter 临时覆盖主题参数（点路径深度合并）
- 一键复制按钮（`navigator.clipboard.write([ClipboardItem('text/html')])` + `execCommand` fallback）
- 硬约束版尾完整性检查（含 `:::interact` 时强制要求 banner / grid / divider / 2 张引导动图）
- 移动端预览容器 375px + iPhone UA

### `text2md`

- `scaffold` 子命令：纯文字稿 → draft.md（含 `![[IMG:id]]` 占位符 + 完整版尾骨架）+ images.json（必有图清单）
- `fill` 子命令：占位符 → 真路径 → final.md
- 链接合法性校验：拒绝 placeholder URL（如缺 mid/idx/sn 的公众号主页 URL、含 TBD/example.com 等关键字）
- agent 决策与用户分工通过 images.json 持久化
