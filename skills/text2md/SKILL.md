---
name: text2md
description: 把纯文字稿转成 md2wechat 标准 markdown + 配图清单。agent 决定哪里需要图、写描述、与用户分工准备，最终拼出可直接喂给 md2wechat 的 final.md
version: 1.0.0
platforms: [macos, linux]
metadata:
  hermes:
    tags: [wechat, publishing, markdown, image-planning, text-to-markdown]
    category: content
    requires_toolsets: [terminal]
    composes_with: [md2wechat]
---

# text2md

把纯文字稿（比如用户写好的几段话）转换成符合 md2wechat 规范的 markdown，包括**配图清单**和**分工决策**。这是 md2wechat 的前置工序。

## When to Use

- 用户给你一段纯文字稿，希望排版成公众号文章但**没有图**
- 用户写好稿子，让你"配图、排版、出 HTML"端到端搞定
- 已经有 markdown 和图了 → 直接用 md2wechat，不需要 text2md

## Workflow（4 个阶段）

```
[用户文字稿.txt]
     ↓ (1) scaffold
[draft.md (含占位符)] + [images.json (清单)] + [images/ 目录]
     ↓ (2) agent 加 inline 占位 + 描述
更新后的 draft.md & images.json
     ↓ (3) 与用户对话分工，回写 owner 字段
images.json 标记每张图谁负责
     ↓ (4) 各自准备图，更新 file 字段 + status=ready
     ↓ fill
[final.md] → md2wechat → HTML
```

### 阶段 1：scaffold（机械生成骨架）

```bash
python3 ~/.hermes/skills/text2md/scripts/plan.py scaffold text.txt --out-dir ./out/
```

输出：
- `out/draft.md`：含 frontmatter + `![[IMG:header]]` 占位符 + 所有原文段落 + 完整版尾骨架
- `out/images.json`：必有图项的清单（header / section_titles / 版尾 6 件套）
- `out/images/`：空目录，存图素材

文字稿格式约定：
- `# 章节名` 标记一级章节标题（自动转章节图占位符）
- `## 子标题` 同理
- 段落用空行分隔
- 不需要的章节不写标题即可

### 阶段 2：agent 决定要插哪些 inline 配图 + 标记关键词

scaffold 不主动插 inline 图（防止机械乱插）。**agent 读完文字稿后自己做两件事**：

#### 2.1 在适当位置插入 inline 图占位符

在 `draft.md` 适当位置插入 `![[IMG:inline-1]]`、`![[IMG:inline-2]]` ...

**配图位置启发式**：
- 主角首次出场段后 → 人物照（owner: user，难生成）
- 重大事件 / 数据节点段后 → 比赛动作图（owner: user）
- 抽象段落 / 情感段 → 意象图（owner: agent，可生成）
- 每 3-5 段配 1 张，密度太高反喧宾夺主

在 `images.json` 的 `items` 数组追加对应的 inline 项：

```json
{
  "id": "inline-1",
  "type": "inline",
  "purpose": "对应原文'外婆是他的拉拉队长'段后的家庭意象图",
  "description": "黑人小男孩与外婆温暖家庭场景，复古色调",
  "recommended_size": "750x500 横",
  "owner": "agent",
  "owner_suggested": "agent",
  "owner_reason": "意象图，无具象人物，agent 可生成",
  "status": "pending",
  "file": null,
  "notes": ""
}
```

#### 2.2 给关键词加强调标记（重要！）

**纯文字稿没有强调标记，agent 必须主动给关键词标 `==红字==` 和 `**黑加粗**`**——否则正文会一片黑字非常单调。

**两层强调系统**：
- `**黑加粗**` → 第一层强调，用于：基础数据（`**1米93**`/`**102公斤**`）、强调论断（`**这是一场战役**`）、引语开头（`**"我向妈妈承诺过……"**`）
- `==红字加粗==` → 第二层强调，用于：**主角姓名首次出现**、**关键成就/数据节点**、**球星技能名**、**重大事件锚点**

**密度参考**：每段 0-2 个强调标记，整篇文章 `**`/`==` 比例约 2:1。

**示例对比**：

| 原始（纯文本，AI 痕迹）| agent 标记后 |
|---|---|
| `他是NBA新生代最具爆炸力的得分后卫，1米93的身高却拥有1米22的恐怖弹跳。` | `他是NBA新生代最具爆炸力的得分后卫，**1米93**的身高却拥有**1米22**的恐怖弹跳。` |
| `他在季后赛总得分超越凯文·加内特，加冕森林狼队史季后赛得分王。` | `==他在季后赛总得分超越凯文·加内特==，加冕森林狼**队史季后赛得分王**。` |
| `他叫安东尼·爱德华兹，绰号"蚁人"。` | `他叫==安东尼·爱德华兹==，绰号"蚁人"。`（主角首次出现，红字）|

**绝对不要**：
- 整段一片标红（破坏可读性）
- 给"的、了、是"等虚词加强调
- 中英文/数字之间空格（这是 AI 痕迹）
- 用英文标点



### 阶段 3：与用户对话分工，回写 images.json

agent 把 `images.json` 给用户看，用类似的话术：

> "我列了 12 张图的清单，建议如下：用户负责 8 张（含品牌资产、人物照），agent 负责 4 张（意象图）。要调整吗？"

用户口头说"X/Y/Z 我来"或"全归你" → agent 修改 `items[i].owner` 字段后写回 `images.json`。**所有变更必须落到文件**（不能只在 chat 里口头确认），后续 fill 检查依据这个文件。

#### 链接获取（重要！agent 不得编造）

带链接的图共两类：
- **header_banner**（版头）：1 个 link_url
- **grid_card**（推文卡）：4 个 link_url（一卡一链）

**这些链接 agent 永远不能自己编造或用 placeholder**，必须主动向用户索取真实 URL：

```
agent: "版头 banner 跳到哪个链接？通常是栏目主页或本期推文 URL。"
user: "https://mp.weixin.qq.com/s/AbCdEfGh"
agent: "好。4 张推文卡分别跳到哪 4 篇过往推文？请按顺序给我 4 个 URL。"
user: "1: https://mp.weixin.qq.com/s/...
       2: ...
       3: ...
       4: ..."
agent: [写入 images.json 各项的 link_url 字段]
```

fill 阶段会检查每个 link_url，**拒绝下列 placeholder**：
- 空值、null
- 含 "placeholder" / "TBD" / "TODO" / "YOUR_URL" / "example.com" 字样
- 公众号主页 URL（仅含 `__biz=` 没有 `mid=`/`idx=`/`sn=`/`/s/<token>`）

如果用户当下没有真实 URL，**留空**或先标记 owner 为 user，让用户后续手动填。**绝不能用任何"测试 URL"凑数**——会导致最终文章里所有图片跳到错误页面。

### 阶段 4：准备图 → fill

各自把图准备好（agent 用生图能力 / 用户从素材库找），按 `id` 命名存到 `out/images/`，例如：
- `out/images/header.png`
- `out/images/section-1-title.png`
- `out/images/inline-1.png`
- ...

然后**更新 images.json**：
- `file`: 改为图片绝对路径或相对 `out/` 的路径
- `status`: 改为 `ready`
- 对 `grid_card` / `footer_guide` 类型还要填 `link_url`

最后：

```bash
python3 ~/.hermes/skills/text2md/scripts/plan.py fill out/
```

`plan.py` 会检查所有占位符对应的 file 是否就绪，缺一项就报错列出。全 ready 后输出 `out/final.md`。

```bash
python3 ~/.hermes/skills/md2wechat/scripts/render.py out/final.md
# → out/final.html，浏览器自动打开
```

## images.json schema

```json
{
  "version": "1.0",
  "source": "text.txt",
  "out_dir": "/path/to/out",
  "created_at": "2026-04-20T...",
  "items": [
    {
      "id": "header",                          // 唯一标识，对应 ![[IMG:header]]
      "type": "header_banner",                  // header_banner/section_title/inline/decorative_banner/grid_card/footer_guide
      "purpose": "公众号栏目品牌标识",            // 一句话用途
      "description": "球场背景 + ...",           // 详细视觉描述（用于生图 prompt 或检索）
      "recommended_size": "750x180",
      "owner": "user",                          // user/agent，对话中可改
      "owner_suggested": "user",                // agent 给的初始建议（保留对照）
      "owner_reason": "品牌资产...",            // 为什么这么建议
      "status": "pending",                      // pending/ready
      "file": null,                             // 准备好后填路径
      "notes": "",                              // 任意备注
      "link_url": null                          // grid_card 和 footer_guide 必填
    }
  ]
}
```

## CLI Reference

```bash
# 阶段 1：从文字稿生成骨架
python3 scripts/plan.py scaffold <text.txt> --out-dir <DIR>

# 阶段 4：占位符 → 真路径 → final.md
python3 scripts/plan.py fill <DIR>
```

## 与 md2wechat 的关系

- text2md 输出 `final.md`，md2wechat 消费 `final.md`
- final.md 是**标准 markdown**，没有 `![[IMG:id]]` 残留，md2wechat 不需要任何改动就能用
- final.md 的版尾结构遵守 md2wechat 的硬约束（scaffold 自动加完整 6 件套）

## 注意

- **占位符 `![[IMG:id]]` 不要直接喂给 md2wechat**，必须先 fill
- **images.json 是 single source of truth**，agent 跟用户对话讨论分工时，**必须把变更写回 json**，不能只在 chat 里说
- agent 写描述时按"生图友好 + 检索友好"的标准（具体名词 + 视觉特征 + 风格关键词）
