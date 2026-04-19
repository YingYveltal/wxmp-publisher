# Changelog

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
