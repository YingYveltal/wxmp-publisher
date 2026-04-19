"""text → 公众号 markdown draft + 配图清单。

三个子命令：
  new <name>                 创建文章工作区（强烈推荐用这个起步）
    在 WXMP_ARTICLES_DIR (默认 ~/wxmp-articles/) 下创建 <YYYY-MM-DD>-<name>/，
    含 source.txt 占位 + images/ 空目录 + .layout 标识文件。
    首次运行会自动创建根目录。

  scaffold <text.txt> [--out-dir DIR]
    解析纯文字稿，生成基础骨架（draft.md + images.json + images/）。
    --out-dir 缺省 = source.txt 所在目录（推荐配合 new 命令使用）。
    检查 .layout 标识文件，不在合法工作区会报错（防 agent 误操作）。

  fill <DIR>
    读 DIR/images.json，用 owner 已 ready 的 file 路径替换 DIR/draft.md 的占位符。
    输出 DIR/final.md，可直接喂给 md2wechat。

agent 推荐工作流：
  1. text2md new "<theme>-<topic>"   → 拿到工作区路径
  2. 把用户稿子写入 <workspace>/source.txt
  3. text2md scaffold <workspace>/source.txt
  4. agent 读完稿子：在 draft.md 适当位置插 ![[IMG:inline-N]] + 给关键词加 ==红字== / **粗体**
  5. 在 images.json items 追加 inline 项（含 description / owner）
  6. 跟用户对话分工，回写 owner / link_url 等字段
  7. 各方准备图，存到 <workspace>/images/，images.json 填 file + status=ready
  8. text2md fill <workspace>
  9. md2wechat render <workspace>/final.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"!\[\[IMG:([\w\-]+)\]\]")
LAYOUT_MARKER = ".layout"  # 工作区合法性标识文件名
DEFAULT_ROOT = Path.home() / "wxmp-articles"


# ---------- 工作区管理 ----------

def get_articles_root() -> Path:
    """返回文章工作区根目录。优先环境变量 WXMP_ARTICLES_DIR。"""
    env = os.environ.get("WXMP_ARTICLES_DIR")
    return Path(env).expanduser().resolve() if env else DEFAULT_ROOT


def ensure_root() -> Path:
    """检查/创建根目录。首次创建时打印友好提示。"""
    root = get_articles_root()
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        print(f"[init] 已创建文章工作区根目录: {root}")
        print(f"       今后所有文章工作区都会在这里。如需更改路径，设环境变量 WXMP_ARTICLES_DIR。")
    return root


def slugify(name: str) -> str:
    """把任意字符串转成文件名安全的 slug：保留中文/字母/数字/-/_，其他换成 -。"""
    s = re.sub(r"[\s/\\:*?\"<>|]+", "-", name.strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"


def is_workspace(path: Path) -> bool:
    """判断 path 是否是合法工作区（含 .layout 标识）。"""
    return (path / LAYOUT_MARKER).is_file()


def find_workspace(path: Path) -> Path | None:
    """从 path 向上查找最近的合法工作区根。找不到返回 None。"""
    p = path.resolve()
    if p.is_file():
        p = p.parent
    while True:
        if is_workspace(p):
            return p
        if p.parent == p:
            return None
        p = p.parent


def cmd_new(name: str) -> dict:
    """创建一个新工作区: <root>/<YYYY-MM-DD>-<slug>/"""
    root = ensure_root()
    today = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(name)
    workspace = root / f"{today}-{slug}"
    if workspace.exists():
        # 同名已存在：加数字后缀
        i = 2
        while (root / f"{today}-{slug}-{i}").exists():
            i += 1
        workspace = root / f"{today}-{slug}-{i}"
    workspace.mkdir(parents=True)
    (workspace / "images").mkdir()
    (workspace / LAYOUT_MARKER).write_text(
        f"wxmp-publisher workspace\ncreated_at: {datetime.now(timezone.utc).isoformat()}\n",
        encoding="utf-8",
    )
    (workspace / "source.txt").write_text(
        "# 在这里粘贴/写入文字稿。\n# 用 markdown 标题语法切章节：\n#   一级章节用 # 标题\n#   二级用 ## 子标题\n# 段落用空行分隔。\n# 不要保留这几行注释。\n\n",
        encoding="utf-8",
    )
    return {"workspace": str(workspace), "root": str(root)}


# ---------- scaffold ----------

def split_into_chapters(text: str) -> list[tuple[str | None, list[str]]]:
    """切成 [(chapter_title_or_None, [paragraphs...]), ...]。

    约定：
    - 章节标题用 markdown `# ` 或 `## ` 标记
    - 段落用空行分隔
    - 第一个章节标题之前的内容算"导语"，title 为 None
    """
    chapters: list[tuple[str | None, list[str]]] = []
    current_title: str | None = None
    current_paras: list[str] = []
    buf: list[str] = []

    def flush_para():
        if buf:
            para = "\n".join(buf).strip()
            if para:
                current_paras.append(para)
            buf.clear()

    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("# ") or stripped.startswith("## "):
            flush_para()
            if current_title is not None or current_paras:
                chapters.append((current_title, current_paras))
            current_title = stripped.lstrip("#").strip()
            current_paras = []
        elif not stripped:
            flush_para()
        else:
            buf.append(stripped)
    flush_para()
    if current_title is not None or current_paras:
        chapters.append((current_title, current_paras))
    return chapters


def make_image_item(id_: str, type_: str, purpose: str, description: str = "",
                    recommended_size: str = "", suggested_owner: str = "user",
                    reason: str = "", **extra) -> dict:
    item = {
        "id": id_,
        "type": type_,
        "purpose": purpose,
        "description": description,
        "recommended_size": recommended_size,
        "owner": suggested_owner,
        "owner_suggested": suggested_owner,
        "owner_reason": reason,
        "status": "pending",
        "file": None,
        "notes": "",
    }
    item.update(extra)
    return item


def scaffold(text_path: Path, out_dir: Path) -> dict:
    text = text_path.read_text(encoding="utf-8")
    chapters = split_into_chapters(text)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "images").mkdir(exist_ok=True)

    # 构建 draft.md
    md_parts: list[str] = []
    md_parts.append("---")
    md_parts.append("theme: edwards")
    md_parts.append("---\n")

    # 1) header
    md_parts.append("![[IMG:header]]\n")

    # 2) 各章节
    section_idx = 0
    for title, paras in chapters:
        if title is not None:
            section_idx += 1
            md_parts.append(f"# ![[IMG:section-{section_idx}-title]]\n")
        for p in paras:
            md_parts.append(p + "\n")

    # 3) 完整版尾骨架（硬约束）
    md_parts.append(_FOOTER_SCAFFOLD)

    draft_md = "\n".join(md_parts) + "\n"
    (out_dir / "draft.md").write_text(draft_md, encoding="utf-8")

    # 构建 images.json
    items: list[dict] = []
    items.append(make_image_item(
        "header", "header_banner",
        "公众号栏目品牌标识 banner（带跳转链接）",
        description="（请补：背景 + 栏目主视觉，如球场/品牌色 + 描边大字）",
        recommended_size="750x180 横长",
        suggested_owner="user",
        reason="品牌资产，需保持视觉一致",
        link_url=None,
        link_url_hint="⚠ agent 必须向用户索取版头 banner 的跳转 URL（通常是栏目主页或本期推文）",
    ))
    for i in range(1, section_idx + 1):
        title_text = chapters[i if chapters[0][0] is None else i - 1][0] if i - 1 < len(chapters) else f"第{i}章"
        # 兼容：如果首块没 title（导语），后续章节索引正确
        with_lead = chapters[0][0] is None
        ch_index = i if with_lead else i - 1
        if 0 <= ch_index < len(chapters):
            title_text = chapters[ch_index][0] or f"第{i}章"
        items.append(make_image_item(
            f"section-{i}-title", "section_title",
            f"第 {i} 章「{title_text}」标题 banner",
            description=f"火焰篮球/品牌模板 + 描边字「{title_text}」",
            recommended_size="1080x250 横长",
            suggested_owner="user",
            reason="需套品牌模板叠章节文字",
        ))

    # 版尾固定 6 件套图项
    items.append(make_image_item(
        "footer-banner", "decorative_banner",
        "互动板块后的'球场热闻'装饰小标识图",
        description="火焰篮球 + '球场热闻'描边字，横长小 banner",
        recommended_size="540x220 横长",
        suggested_owner="user",
        reason="品牌资产",
    ))
    for i in range(1, 5):
        items.append(make_image_item(
            f"grid-{i}", "grid_card",
            f"2x2 推文卡第 {i} 张（带跳转链接）",
            description="（请补：过往推文封面图）",
            recommended_size="540x230 横长（自动 cover 裁切到 2.3:1）",
            suggested_owner="user",
            reason="过往推文封面，从历史文章中选",
            link_url=None,
            link_url_hint=f"⚠ agent 必须向用户索取第 {i} 张推文卡跳转的真实推文 URL（带 mid/idx/sn 参数）",
            grid_title=f"过往推文 {i} 标题",
        ))
    items.append(make_image_item(
        "guide-1", "footer_guide",
        "引导动图 1（如'点亮星标'）",
        description="点亮星标 / 关注引导 + 二维码 GIF",
        recommended_size="750x500",
        suggested_owner="user",
        reason="品牌固定素材",
    ))
    items.append(make_image_item(
        "guide-2", "footer_guide",
        "引导动图 2（如活动横条）",
        description="活动 / 派对推广 banner GIF",
        recommended_size="750x250",
        suggested_owner="user",
        reason="品牌固定素材",
    ))

    images_data = {
        "version": "1.0",
        "source": str(text_path),
        "out_dir": str(out_dir),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "schema_hint": (
            "agent 决定要插 inline 配图时，往 items 追加 type=inline 的项，"
            "并在 draft.md 对应位置插 ![[IMG:<id>]] 占位符。"
            "对话分工时改 owner 字段（user/agent），准备好图后填 file 路径并把 status 改 ready。"
        ),
        "items": items,
    }
    (out_dir / "images.json").write_text(
        json.dumps(images_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "draft_md": str(out_dir / "draft.md"),
        "images_json": str(out_dir / "images.json"),
        "images_dir": str(out_dir / "images"),
        "chapters": section_idx,
        "items": len(items),
    }


_FOOTER_SCAFFOLD = """
::: interact
==【今日互动】==
==（请补：互动话题问句 1，红字）==
==（请补：互动话题问句 2，红字）==
欢迎在评论区留言分享
抽1位街球手送出==【派对会员(30R)】==1份
:::

::: banner
![[IMG:footer-banner]]
:::

::: grid
[![过往推文1标题](IMG_GRID_1)](GRID_URL_1)
[![过往推文2标题](IMG_GRID_2)](GRID_URL_2)
[![过往推文3标题](IMG_GRID_3)](GRID_URL_3)
[![过往推文4标题](IMG_GRID_4)](GRID_URL_4)
:::

::: divider
:::

![[IMG:guide-1]]

![[IMG:guide-2]]
"""


# ---------- fill ----------

def _is_valid_link(url: str | None, item_id: str) -> tuple[bool, str]:
    """检查 link_url 是否真实可用。返回 (合法, 原因)。

    拒绝以下"看起来是 placeholder"的 URL：
    - None / 空串
    - 形如 https://mp.weixin.qq.com/s?__biz=XXX== 但**没有** mid/idx/sn 参数
      （这是公众号主页 URL，通常不是单篇文章链接）
    - 含 'placeholder' / 'TBD' / 'TODO' / 'YOUR_URL' 字样
    - mp.weixin.qq.com/s/<token> 中 token 看起来是连续重复字符 / 字母数字递增模式
      （典型 placeholder：AbCd1111111111111 / abc123456789）
    """
    if not url:
        return False, "link_url 为空"
    if not url.startswith(("http://", "https://")):
        return False, f"link_url 不是合法 URL: {url[:60]}"
    bad_markers = ("placeholder", "TBD", "TODO", "YOUR_URL", "example.com")
    for m in bad_markers:
        if m.lower() in url.lower():
            return False, f"link_url 含 placeholder 标记 '{m}'"
    # 公众号主页 URL（不带 mid/idx/sn）通常不是单篇推文链接
    if "mp.weixin.qq.com" in url and item_id.startswith(("grid-", "header")):
        if not any(p in url for p in ("mid=", "idx=", "sn=", "/s/")):
            return False, (
                f"link_url 看起来是公众号主页 URL（缺 mid/idx/sn 参数），"
                f"不是单篇推文链接: {url[:80]}"
            )
        # 检查 /s/<token>: 真实 mp 推文 token 是 22 位混合字符串，
        # 拒绝明显的 placeholder 模式（连续重复字符、递增序列）
        m = re.search(r"/s/([A-Za-z0-9_\-]+)", url)
        if m:
            token = m.group(1)
            if len(set(token)) < 5:
                return False, f"link_url 的 token 重复字符过多，看起来是测试值: {url}"
            # 含 4+ 连续相同字符（如 11111）
            if re.search(r"(.)\1{3,}", token):
                return False, f"link_url 的 token 含连续重复字符（如 11111），看起来是测试值: {url}"
            # 含 4+ 连续递增字符（如 1234, abcd）
            chars = list(token.lower())
            for i in range(len(chars) - 3):
                if all(ord(chars[i+j+1]) - ord(chars[i+j]) == 1 for j in range(3)):
                    return False, f"link_url 的 token 含连续递增字符（如 1234/abcd），看起来是测试值: {url}"
    return True, ""


def fill(out_dir: Path) -> dict:
    draft_path = out_dir / "draft.md"
    images_path = out_dir / "images.json"
    if not draft_path.exists():
        raise SystemExit(f"draft 不存在: {draft_path}")
    if not images_path.exists():
        raise SystemExit(f"images.json 不存在: {images_path}")

    images_data = json.loads(images_path.read_text(encoding="utf-8"))
    items = {it["id"]: it for it in images_data.get("items", [])}

    # 检查所有 ![[IMG:id]] 占位符在 images.json 里都有 file 且 status=ready；header 还要 link_url
    md = draft_path.read_text(encoding="utf-8")
    placeholders = PLACEHOLDER_RE.findall(md)
    missing: list[str] = []
    MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 公众号粘贴单图硬上限
    for pid in set(placeholders):
        it = items.get(pid)
        if not it:
            missing.append(f"  - ![[IMG:{pid}]] 在 images.json 里没有对应项")
        elif not it.get("file"):
            missing.append(f"  - {pid} ({it['purpose']}): 缺 file 路径")
        elif it.get("status") != "ready":
            missing.append(f"  - {pid} ({it['purpose']}): status={it.get('status')}（需 ready）")
        else:
            # 大小预检：超过 5MB 公众号粘贴会失败
            try:
                fp = Path(it["file"]).expanduser()
                if fp.exists():
                    sz = fp.stat().st_size
                    if sz > MAX_IMAGE_BYTES:
                        missing.append(
                            f"  - {pid} ({it['purpose']}): 图片 {fp.name} {sz/1024/1024:.1f}MB，"
                            f"超过公众号粘贴 5MB 上限，必须压缩"
                        )
            except Exception:
                pass
        # header 必须有合法 link_url
        if it and it.get("type") == "header_banner":
            ok, reason = _is_valid_link(it.get("link_url"), pid)
            if not ok:
                missing.append(f"  - {pid} (版头): {reason} —— agent 必须主动向用户索取真实跳转 URL")

    # 同时检查 grid 的特殊占位（IMG_GRID_N + GRID_URL_N）；引导动图改用 ![[IMG:guide-N]] 走通用通道
    grid_url_placeholders = re.findall(r"GRID_URL_(\d+)", md)
    img_grid_placeholders = re.findall(r"IMG_GRID_(\d+)", md)

    for n in set(img_grid_placeholders):
        it = items.get(f"grid-{n}")
        if not it or not it.get("file") or it.get("status") != "ready":
            missing.append(f"  - grid-{n}: 缺 file 或 status 非 ready")
        else:
            try:
                fp = Path(it["file"]).expanduser()
                if fp.exists():
                    sz = fp.stat().st_size
                    if sz > MAX_IMAGE_BYTES:
                        missing.append(
                            f"  - grid-{n}: 图片 {fp.name} {sz/1024/1024:.1f}MB，"
                            f"超过公众号粘贴 5MB 上限，必须压缩"
                        )
            except Exception:
                pass
    for n in set(grid_url_placeholders):
        it = items.get(f"grid-{n}")
        if not it:
            missing.append(f"  - grid-{n}: images.json 里无此项")
            continue
        ok, reason = _is_valid_link(it.get("link_url"), f"grid-{n}")
        if not ok:
            missing.append(f"  - grid-{n} (推文卡 {n}): {reason} —— agent 必须向用户索取真实推文 URL")

    if missing:
        raise SystemExit(
            "[fill] 配图未就绪，缺少以下：\n" + "\n".join(missing) +
            "\n\n请在 images.json 里给对应项填上 file 路径，把 status 改为 ready，"
            "（grid/guide 还需 link_url），再重新运行 fill。"
        )

    # 替换 ![[IMG:id]] → markdown image 语法
    # - header_banner（带链接）→ [![alt](file)](url)
    # - 其他（section_title / inline / decorative_banner）→ ![](file)
    def repl(m: re.Match) -> str:
        it = items[m.group(1)]
        file = it["file"]
        alt = it.get("description", "") or it.get("purpose", "")
        # 转义 alt 里的方括号防止破坏 markdown
        alt = alt.replace("[", "").replace("]", "").replace("(", "").replace(")", "")
        if it["type"] == "header_banner" and it.get("link_url"):
            return f'[![{alt}]({file})]({it["link_url"]})'
        return f'![{alt}]({file})'
    out_md = PLACEHOLDER_RE.sub(repl, md)

    # 替换 IMG_GRID_N / GRID_URL_N（grid 内部专用占位符）
    for n in set(img_grid_placeholders):
        out_md = out_md.replace(f"IMG_GRID_{n}", items[f"grid-{n}"]["file"])
    for n in set(grid_url_placeholders):
        out_md = out_md.replace(f"GRID_URL_{n}", items[f"grid-{n}"]["link_url"])

    # grid 标题用 grid-N 项的 grid_title 替换
    for n in set(img_grid_placeholders):
        title = items[f"grid-{n}"].get("grid_title") or f"推文{n}"
        out_md = out_md.replace(f"过往推文{n}标题", title)

    final_path = out_dir / "final.md"
    final_path.write_text(out_md, encoding="utf-8")
    return {"final_md": str(final_path), "replaced": len(set(placeholders))}


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description="text → 公众号 markdown draft + 配图清单")
    sub = ap.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="创建文章工作区（推荐起步）")
    n.add_argument("name", help="文章主题，会被转成 slug。例：'edwards-超越加内特'")

    s = sub.add_parser("scaffold", help="文字稿 → draft.md + images.json")
    s.add_argument("text_path", help="source.txt 路径（通常在工作区里）")
    s.add_argument("--out-dir", "-o", default=None,
                   help="输出目录，缺省 = source.txt 所在目录（推荐配合 new 使用）")

    f = sub.add_parser("fill", help="占位符 → 真路径 → final.md")
    f.add_argument("out_dir", help="工作区目录")

    args = ap.parse_args()

    if args.cmd == "new":
        result = cmd_new(args.name)
        ws = result["workspace"]
        print(f"[ok] 工作区已创建: {ws}")
        print(f"\n下一步：")
        print(f"  1. 把文字稿写入 {ws}/source.txt（覆盖默认占位）")
        print(f"  2. python3 {__file__} scaffold {ws}/source.txt")
        print(f"  3. agent 读 draft.md 加 inline 占位 + 标关键词 + 写 images.json")
        print(f"  4. 准备图存到 {ws}/images/")
        print(f"  5. python3 {__file__} fill {ws}")
        print(f"  6. python3 ~/.hermes/skills/md2wechat/scripts/render.py {ws}/final.md")

    elif args.cmd == "scaffold":
        text_path = Path(args.text_path).expanduser().resolve()
        if not text_path.exists():
            raise SystemExit(f"text 不存在: {text_path}")
        # 默认 out-dir = source 所在目录
        out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else text_path.parent
        # 检查工作区合法性
        ws = find_workspace(out_dir)
        if ws is None:
            root = get_articles_root()
            raise SystemExit(
                f"[scaffold] 不在合法工作区！\n"
                f"  当前 out-dir: {out_dir}\n"
                f"  没有找到 .layout 标识文件。\n\n"
                f"请先用 new 命令创建工作区：\n"
                f"  python3 {__file__} new \"<文章主题>\"\n\n"
                f"或在已有工作区下放置 source.txt 后再跑 scaffold。\n"
                f"工作区根目录默认在 {root}，可通过 WXMP_ARTICLES_DIR 覆盖。"
            )
        if ws != out_dir:
            print(f"[info] 检测到工作区: {ws}（out-dir 自动用此）")
            out_dir = ws
        result = scaffold(text_path, out_dir)
        print(f"[ok] scaffold:")
        print(f"  draft:  {result['draft_md']}")
        print(f"  images.json: {result['images_json']} ({result['items']} 项)")
        print(f"  images dir:  {result['images_dir']}")
        print(f"  章节数: {result['chapters']}")
        print(f"\n下一步：")
        print(f"  1. agent 读 {result['draft_md']}，决定要插 inline 配图，往 images.json 追加 inline 项 + 在 draft 里插 ![[IMG:<id>]]")
        print(f"  2. agent 与用户对话分工，回写 images.json 的 owner 字段")
        print(f"  3. 准备好图存到 {result['images_dir']}/，在 images.json 里填 file 路径并把 status 改 ready")
        print(f"  4. python3 {__file__} fill {out_dir}")

    elif args.cmd == "fill":
        out_dir = Path(args.out_dir).expanduser().resolve()
        # 检查工作区合法性
        if not is_workspace(out_dir):
            ws = find_workspace(out_dir)
            if ws is None:
                raise SystemExit(
                    f"[fill] 不是合法工作区: {out_dir}\n"
                    f"缺少 .layout 标识文件。请确认路径，或用 new 命令创建。"
                )
            out_dir = ws
        result = fill(out_dir)
        print(f"[ok] final.md 已生成: {result['final_md']} ({result['replaced']} 个占位符替换)")
        print(f"下一步: python3 ~/.hermes/skills/md2wechat/scripts/render.py {result['final_md']}")


if __name__ == "__main__":
    main()
