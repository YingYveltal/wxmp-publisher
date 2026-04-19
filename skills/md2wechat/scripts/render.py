"""Markdown → 公众号可粘贴 HTML。

策略：
1. markdown-it-py 解析成 token 流（不是 AST，更顺手）。
2. 自定义遍历器：每碰到一个块级节点，按节点类型从 theme 里取对应模板片段，
   渲染后追加到输出。行内 token 一并消费。
3. 行内样式（strong / em / code / link）按 theme.inline.* 用 inline style 包裹。
4. 图片 src 经 img.py 转 base64。
5. 整个文档外层包一个 article wrapper section。

输出特点：纯 <section> + inline style，符合公众号编辑器要求。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markdown_it import MarkdownIt
from mdit_py_plugins.container import container_plugin

from img import to_data_uri

SHARED_TEMPLATES = Path(__file__).resolve().parents[1] / "themes"


# 一键复制脚本：选中 .paper 内的 article wrapper section（不含 .paper 容器），
# 用 navigator.clipboard.write([ClipboardItem('text/html')]) 写剪贴板。
# 公众号编辑器读 text/html MIME 自动还原 inline style。
# fallback: contenteditable + selection + execCommand('copy')，老浏览器/file:// 受限场景兜底。
_COPY_SCRIPT = """
<script>
(function(){
  const btn = document.getElementById('copy-btn');
  const tip = document.getElementById('copy-tip');
  function flash(text, klass, ms){
    btn.textContent = text;
    btn.className = klass || '';
    setTimeout(()=>{btn.textContent='📋 复制到公众号';btn.className='';}, ms||2000);
  }
  function showTip(msg){
    tip.textContent = msg; tip.style.display = 'block';
    setTimeout(()=>{tip.style.display='none';}, 4000);
  }
  btn.addEventListener('click', async () => {
    const article = document.querySelector('.paper > section');
    if (!article) { flash('❌ 没找到内容', 'error'); return; }
    const html = article.outerHTML;
    const text = article.innerText;
    // 优先用现代 Clipboard API（保留 text/html MIME）
    if (navigator.clipboard && window.ClipboardItem) {
      try {
        await navigator.clipboard.write([new ClipboardItem({
          'text/html': new Blob([html], {type:'text/html'}),
          'text/plain': new Blob([text], {type:'text/plain'}),
        })]);
        flash('✅ 已复制到剪贴板', 'success');
        showTip('打开 mp.weixin.qq.com 后台编辑器，光标定位到正文区，Cmd/Ctrl+V 粘贴即可');
        return;
      } catch(e) { console.warn('clipboard.write 失败，尝试 fallback', e); }
    }
    // Fallback: 选中 article 节点 + execCommand('copy')
    try {
      const range = document.createRange();
      range.selectNode(article);
      const sel = getSelection();
      sel.removeAllRanges(); sel.addRange(range);
      const ok = document.execCommand('copy');
      sel.removeAllRanges();
      if (ok) { flash('✅ 已复制（兼容模式）', 'success');
        showTip('打开 mp.weixin.qq.com 后台编辑器粘贴即可'); }
      else { throw new Error('execCommand 返回 false'); }
    } catch(e) {
      flash('❌ 复制失败', 'error');
      showTip('请手动选中正文 Cmd/Ctrl+A → C 再粘贴。失败原因：' + e.message);
      console.error(e);
    }
  });
})();
</script>
"""


def load_theme(theme: str) -> tuple[dict, Environment]:
    theme_dir = SHARED_TEMPLATES / theme
    if not theme_dir.is_dir():
        raise SystemExit(f"theme not found: {theme_dir}")
    manifest = json.loads((theme_dir / "manifest.json").read_text(encoding="utf-8"))
    env = Environment(
        loader=FileSystemLoader(str(theme_dir)),
        autoescape=False,  # 我们自己在 render_inline 里用 html.escape 控制文本节点
        keep_trailing_newline=False,
    )
    return manifest, env


def render_template(env: Environment, manifest: dict, kind: str, **vars) -> str:
    """kind 形如 'title_h1'/'title_h2'/'quote'/'divider'/'caption'/'body'。"""
    name = manifest["defaults"].get(kind)
    if not name:
        raise SystemExit(f"theme manifest 没有为 {kind} 指定 default")
    # title_h1 → 子目录是 'title'
    folder = kind.split("_", 1)[0]
    tpl = env.get_template(f"{folder}/{name}.html.j2")
    return tpl.render(**vars).strip()


# ---------- 行内 token → HTML 字符串 ----------

def render_inline(tokens, manifest: dict, base_dir: Path) -> str:
    """把 markdown-it 的 inline children token 列表渲染成 HTML 片段。"""
    out: list[str] = []
    inline_style = manifest.get("inline", {})
    img_style = manifest.get("image", {}).get("img_style", "max-width:100%;height:auto;")

    # 简易栈：跟踪当前打开的 inline 标签
    open_stack: list[str] = []

    for tok in tokens:
        t = tok.type
        if t == "text":
            # 处理 ==text== 高亮语法：拆成 text + <span 红粗> + text
            content = tok.content
            mark_style = inline_style.get("mark_style", "color:#ba0808;font-weight:bold;")
            parts = re.split(r"==([^=]+)==", content)
            for i, p in enumerate(parts):
                if i % 2 == 0:
                    if p:
                        out.append(html.escape(p))
                else:
                    out.append(f'<span style="{mark_style}">{html.escape(p)}</span>')
        elif t == "softbreak" or t == "hardbreak":
            out.append("<br/>")
        elif t == "code_inline":
            style = inline_style.get("code_style", "")
            out.append(f'<code style="{style}">{html.escape(tok.content)}</code>')
        elif t == "strong_open":
            style = inline_style.get("strong_style", "font-weight:bold;")
            out.append(f'<strong style="{style}">')
            open_stack.append("strong")
        elif t == "strong_close":
            out.append("</strong>")
            if open_stack and open_stack[-1] == "strong":
                open_stack.pop()
        elif t == "em_open":
            style = inline_style.get("em_style", "font-style:italic;")
            out.append(f'<em style="{style}">')
            open_stack.append("em")
        elif t == "em_close":
            out.append("</em>")
            if open_stack and open_stack[-1] == "em":
                open_stack.pop()
        elif t == "s_open":
            out.append('<span style="text-decoration:line-through;">')
            open_stack.append("s")
        elif t == "s_close":
            out.append("</span>")
            if open_stack and open_stack[-1] == "s":
                open_stack.pop()
        elif t == "link_open":
            href = html.escape(tok.attrGet("href") or "")
            style = inline_style.get("link_style", "color:#07c160;")
            out.append(f'<a href="{href}" style="{style}">')
            open_stack.append("a")
        elif t == "link_close":
            out.append("</a>")
            if open_stack and open_stack[-1] == "a":
                open_stack.pop()
        elif t == "image":
            src = to_data_uri(tok.attrGet("src") or "", base_dir)
            alt = html.escape(tok.content or "")
            out.append(f'<img src="{src}" alt="{alt}" style="{img_style}"/>')
        elif t == "html_inline":
            # 用户在 markdown 里直接写的 HTML，原样保留
            out.append(tok.content)
        else:
            # 未识别的 inline token，安全降级为文本
            if tok.content:
                out.append(html.escape(tok.content))
    return "".join(out)


# ---------- 块级遍历 ----------

def is_caption_paragraph(inline_children) -> bool:
    """图注启发式：段落只含一个 image 节点，或一个 image + 紧邻一个 em 文本。

    更严谨地说：markdown 里 ![alt](img.png) 单独一段被视作配图；
    紧跟下一段如果是纯 *italic 文本* 也被视作图注（在 walk 里特殊处理）。
    """
    only = [c for c in inline_children if c.type != "softbreak" and c.type != "hardbreak"]
    return len(only) == 1 and only[0].type == "image"


def is_linked_image_paragraph(inline_children) -> tuple[bool, str | None, object | None]:
    """段落只含 link_open + image + link_close 的情况——版头/版尾的标准 markdown 写法。
    返回 (是否匹配, href, image_token)。
    """
    only = [c for c in inline_children if c.type not in ("softbreak", "hardbreak")]
    if len(only) == 3 and only[0].type == "link_open" and only[1].type == "image" and only[2].type == "link_close":
        return True, only[0].attrGet("href"), only[1]
    return False, None, None


def is_pure_italic_paragraph(inline_children) -> bool:
    """段落只含一对 em_open/em_close 和文本/inline。"""
    if not inline_children:
        return False
    if inline_children[0].type != "em_open" or inline_children[-1].type != "em_close":
        return False
    return True


def render_blocks(tokens, manifest: dict, env: Environment, base_dir: Path) -> str:
    out: list[str] = []
    i = 0
    n = len(tokens)
    last_was_image = False

    while i < n:
        tok = tokens[i]
        t = tok.type

        if t == "heading_open":
            level = int(tok.tag[1])  # h1 -> 1
            inline = tokens[i + 1].children or []
            # 特例：如果 heading 内容只是一个 image（# ![](banner.png) 写法），
            # 渲染为图片 banner，绕过 title 模板
            non_break = [c for c in inline if c.type not in ("softbreak", "hardbreak")]
            if len(non_break) == 1 and non_break[0].type == "image":
                src_tok = non_break[0]
                src = to_data_uri(src_tok.attrGet("src") or "", base_dir)
                alt = html.escape(src_tok.content or "")
                wrapper = manifest.get("title_image", {}).get(
                    "wrapper_style",
                    "margin: 28px 0 12px; text-align: center; line-height: 0;",
                )
                img_style = manifest.get("title_image", {}).get(
                    "img_style",
                    "max-width: 100%; height: auto; display: inline-block;",
                )
                out.append(
                    f'<section style="{wrapper}"><img src="{src}" alt="{alt}" style="{img_style}"/></section>'
                )
            else:
                text = render_inline(inline, manifest, base_dir)
                kind = "title_h1" if level == 1 else ("title_h2" if level == 2 else "title_h3")
                out.append(render_template(env, manifest, kind, title=text))
            i += 3  # heading_open / inline / heading_close
            last_was_image = False
            continue

        if t == "paragraph_open":
            inline_tok = tokens[i + 1]
            children = inline_tok.children or []

            # 1) [![alt](img)](url) 单独成段：版头/版尾，输出居中带链接的图
            is_link_img, href, img_tok = is_linked_image_paragraph(children)
            if is_link_img and img_tok is not None:
                src = to_data_uri(img_tok.attrGet("src") or "", base_dir)
                alt = html.escape(img_tok.content or "")
                href_safe = html.escape(href or "")
                wrapper = manifest.get("image", {}).get("wrapper_style", "text-align:center;margin:16px 0;")
                img_style = manifest.get("image", {}).get("img_style", "max-width:100%;height:auto;")
                out.append(
                    f'<section style="{wrapper}">'
                    f'<a href="{href_safe}" style="display:inline-block;line-height:0;">'
                    f'<img src="{src}" alt="{alt}" style="{img_style}"/>'
                    f'</a></section>'
                )
                last_was_image = True
            elif is_caption_paragraph(children):
                # 图片段落：拆成 image + 不套 body 模板
                src_tok = next(c for c in children if c.type == "image")
                src = to_data_uri(src_tok.attrGet("src") or "", base_dir)
                alt = html.escape(src_tok.content or "")
                wrapper = manifest.get("image", {}).get("wrapper_style", "text-align:center;margin:16px 0;")
                img_style = manifest.get("image", {}).get("img_style", "max-width:100%;height:auto;")
                out.append(
                    f'<section style="{wrapper}"><img src="{src}" alt="{alt}" style="{img_style}"/></section>'
                )
                last_was_image = True
            elif last_was_image and is_pure_italic_paragraph(children):
                # 上一段是图，这段是 *斜体* → 当作图注
                # 取出 em 之间的内容重新渲染
                inner = children[1:-1]
                content = render_inline(inner, manifest, base_dir)
                out.append(render_template(env, manifest, "caption", content=content))
                last_was_image = False
            else:
                content = render_inline(children, manifest, base_dir)
                out.append(render_template(env, manifest, "body", content=content))
                last_was_image = False
            i += 3
            continue

        if t == "blockquote_open":
            # 找到匹配的 blockquote_close
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                if tokens[j].type == "blockquote_open":
                    depth += 1
                elif tokens[j].type == "blockquote_close":
                    depth -= 1
                if depth == 0:
                    break
                j += 1
            inner_tokens = tokens[i + 1 : j]
            # 如果引用内只有一个段落，直接用 inline 渲染避免多嵌一层 section
            inner_paragraphs = [k for k, tk in enumerate(inner_tokens) if tk.type == "paragraph_open"]
            if len(inner_paragraphs) == 1 and all(
                tk.type in ("paragraph_open", "inline", "paragraph_close") for tk in inner_tokens
            ):
                inline_tok = inner_tokens[1]
                inner = render_inline(inline_tok.children or [], manifest, base_dir)
            else:
                inner = render_blocks(inner_tokens, manifest, env, base_dir)
            out.append(render_template(env, manifest, "quote", content=inner))
            i = j + 1
            last_was_image = False
            continue

        if t == "hr":
            out.append(render_template(env, manifest, "divider"))
            i += 1
            last_was_image = False
            continue

        if t == "bullet_list_open" or t == "ordered_list_open":
            ordered = t == "ordered_list_open"
            close_type = "ordered_list_close" if ordered else "bullet_list_close"
            depth = 1
            j = i + 1
            while j < n:
                if tokens[j].type == t:
                    depth += 1
                elif tokens[j].type == close_type:
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            list_html = render_list(tokens[i : j + 1], manifest, base_dir, ordered)
            out.append(list_html)
            i = j + 1
            last_was_image = False
            continue

        if t == "fence" or t == "code_block":
            style = manifest.get("code_block_style", "background:#f4f4f4;padding:8px;")
            code = html.escape(tok.content.rstrip("\n"))
            out.append(f'<section style="{style}"><pre style="margin:0;white-space:pre-wrap;"><code>{code}</code></pre></section>')
            i += 1
            last_was_image = False
            continue

        if t == "html_block":
            out.append(tok.content)
            i += 1
            last_was_image = False
            continue

        # ::: name container 处理（interact/grid/divider/center）
        if t.startswith("container_") and t.endswith("_open"):
            name = t[len("container_"):-len("_open")]
            close_type = f"container_{name}_close"
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                if tokens[j].type == t:
                    depth += 1
                elif tokens[j].type == close_type:
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            inner_tokens = tokens[i + 1 : j]
            out.append(render_container(name, inner_tokens, manifest, env, base_dir))
            i = j + 1
            last_was_image = False
            continue

        # 其他未处理 token 跳过
        i += 1

    return "\n".join(out)


def render_container(name: str, inner_tokens, manifest: dict, env: Environment, base_dir: Path) -> str:
    """处理 ::: name ... ::: 容器。

    - interact: 居中互动板块。每行一段，自动识别【...】或全段红字加粗
    - grid: 2x2 图片网格 + 标题。每段写两个图，用 | 分隔（或顺序两个 image）
    - divider: 红色细线分割（带闪电装饰）
    - center: 居中文案
    """
    if name == "divider":
        cfg = manifest.get("red_divider", {})
        c = cfg.get("color", "#ba0808")
        return (
            f'<section style="margin: 18px 0; text-align: center; line-height: 0;">'
            f'<section style="display: inline-block; width: 38%; height: 1px; background: {c}; vertical-align: middle;"></section>'
            f'<section style="display: inline-block; margin: 0 8px; width: 6px; height: 6px; background: {c}; transform: rotate(45deg); vertical-align: middle;"></section>'
            f'<section style="display: inline-block; width: 38%; height: 1px; background: {c}; vertical-align: middle;"></section>'
            f'</section>'
        )

    if name == "interact":
        cfg = manifest.get("interact", {})
        wrapper_style = cfg.get("wrapper_style", "margin: 20px 0; text-align: center; line-height: 1.9;")
        line_style = cfg.get("line_style", "color: #222; font-size: 14px;")
        out = [f'<section style="{wrapper_style}">']
        for tok in inner_tokens:
            if tok.type == "inline":
                line = render_inline(tok.children or [], manifest, base_dir)
                out.append(f'<section style="{line_style}">{line}</section>')
        out.append("</section>")
        return "".join(out)

    if name == "grid":
        cfg = manifest.get("grid", {})
        gap = cfg.get("gap", "8px")
        # 钉死图片比例 (width:height)，cell 内任何尺寸的图都被 cover 裁切
        aspect = float(cfg.get("aspect", 2.3))
        padding_bottom = f"{100.0/aspect:.1f}%"
        title_style = cfg.get("title_style", "margin: 4px 0 0; text-align: center; font-size: 13px; color: #222;")
        items: list[tuple[str, str, str | None]] = []  # (src, title, href)
        for tok in inner_tokens:
            if tok.type != "inline":
                continue
            children = tok.children or []
            k = 0
            while k < len(children):
                c = children[k]
                if (c.type == "link_open" and k + 2 < len(children)
                        and children[k+1].type == "image"
                        and children[k+2].type == "link_close"):
                    href = c.attrGet("href")
                    img_tok = children[k+1]
                    src = to_data_uri(img_tok.attrGet("src") or "", base_dir)
                    title = html.escape(img_tok.content or "")
                    items.append((src, title, href))
                    k += 3
                elif c.type == "image":
                    src = to_data_uri(c.attrGet("src") or "", base_dir)
                    title = html.escape(c.content or "")
                    items.append((src, title, None))
                    k += 1
                else:
                    k += 1
        rows: list[str] = []
        for r in range(0, len(items), 2):
            row_items = items[r:r+2]
            cells = []
            for src, title, href in row_items:
                # 钉死比例：padding-bottom 撑出容器高度，img 绝对定位 cover 裁切
                box = (
                    f'<section style="position:relative;padding-bottom:{padding_bottom};background:#f4f4f4;overflow:hidden;line-height:0;">'
                    f'<img src="{src}" style="position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;display:block;"/>'
                    f'</section>'
                )
                if href:
                    box = f'<a href="{html.escape(href)}" style="display:block;line-height:0;">{box}</a>'
                cells.append(
                    f'<section style="flex:1;min-width:0;">'
                    f'{box}'
                    f'<section style="{title_style}">{title}</section>'
                    f'</section>'
                )
            while len(cells) < 2:
                cells.append('<section style="flex:1;"></section>')
            rows.append(
                f'<section style="display:flex;gap:{gap};margin-top:{gap};align-items:flex-start;">{cells[0]}{cells[1]}</section>'
            )
        return f'<section style="margin: 12px 0;">{"".join(rows)}</section>'

    if name == "banner":
        # 装饰性小 banner（如"球场热闻"标识图）：
        # 公众号编辑器会丢/覆盖 img 上的 max-width:%，必须用"外层 section 限宽 + img width:100%"结构
        cfg = manifest.get("banner", {})
        max_width = cfg.get("max_width", "30%")
        wrapper_style = cfg.get("wrapper_style", "margin: 18px 0 6px; text-align: center; line-height: 0;")
        items: list[tuple[str, str | None]] = []  # (src, href)
        for tok in inner_tokens:
            if tok.type != "inline":
                continue
            children = tok.children or []
            k = 0
            while k < len(children):
                c = children[k]
                if (c.type == "link_open" and k + 2 < len(children)
                        and children[k+1].type == "image"
                        and children[k+2].type == "link_close"):
                    src = to_data_uri(children[k+1].attrGet("src") or "", base_dir)
                    items.append((src, c.attrGet("href")))
                    k += 3
                elif c.type == "image":
                    src = to_data_uri(c.attrGet("src") or "", base_dir)
                    items.append((src, None))
                    k += 1
                else:
                    k += 1
        out = [f'<section style="{wrapper_style}">']
        for src, href in items:
            inner = (
                f'<section style="display:inline-block;width:{max_width};line-height:0;vertical-align:middle;">'
                f'<img src="{src}" style="width:100%;height:auto;display:block;"/>'
                f'</section>'
            )
            if href:
                inner = f'<a href="{html.escape(href)}" style="display:inline-block;width:{max_width};line-height:0;">{inner}</a>'
            out.append(inner)
        out.append("</section>")
        return "".join(out)

    if name == "center":
        cfg = manifest.get("center", {})
        wrapper_style = cfg.get("wrapper_style", "margin: 14px 0; text-align: center;")
        out = [f'<section style="{wrapper_style}">']
        for tok in inner_tokens:
            if tok.type == "inline":
                out.append(render_inline(tok.children or [], manifest, base_dir))
                out.append("<br/>")
        out.append("</section>")
        return "".join(out)

    # 未知 container：当作普通段落渲染
    return render_blocks(inner_tokens, manifest, env, base_dir)


def render_list(tokens, manifest: dict, base_dir: Path, ordered: bool) -> str:
    """简版列表：保留 ul/ol/li，不做嵌套样式优化。"""
    list_cfg = manifest.get("list", {})
    tag = "ol" if ordered else "ul"
    style = list_cfg.get(f"{tag}_style", "padding-left:24px;")
    li_style = list_cfg.get("li_style", "")

    out = [f'<{tag} style="{style}">']
    i = 1  # 跳过开标签
    n = len(tokens) - 1  # 跳过末尾闭标签
    while i < n:
        tok = tokens[i]
        if tok.type == "list_item_open":
            # 找到匹配的 list_item_close
            depth = 1
            j = i + 1
            while j < n:
                if tokens[j].type == "list_item_open":
                    depth += 1
                elif tokens[j].type == "list_item_close":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            # list_item 里通常是 paragraph_open/inline/paragraph_close，提取 inline
            inner_html_parts: list[str] = []
            k = i + 1
            while k < j:
                if tokens[k].type == "inline":
                    inner_html_parts.append(render_inline(tokens[k].children or [], manifest, base_dir))
                k += 1
            out.append(f'<li style="{li_style}">{"".join(inner_html_parts)}</li>')
            i = j + 1
        else:
            i += 1
    out.append(f"</{tag}>")
    return "".join(out)


# ---------- 主入口 ----------

def parse_frontmatter(md_text: str) -> tuple[dict, str]:
    """简易 yaml frontmatter 解析。

    支持的字段：
      theme: 主题名（覆盖 CLI --theme）
      overrides:
        path.to.field: value     # 点路径深度合并到 manifest

    格式：文件首行是 `---`，紧接 yaml，再 `---` 结束。其余是正文。
    yaml 不依赖 PyYAML，只支持平的 key:value（值可以是字符串、数字、布尔），
    overrides 用 `parent.child: value` 平铺写法（不支持嵌套缩进）。
    """
    if not md_text.startswith("---\n"):
        return {}, md_text
    end = md_text.find("\n---\n", 4)
    if end < 0:
        return {}, md_text
    fm_text = md_text[4:end]
    body = md_text[end + 5:]

    meta: dict = {}
    in_overrides = False
    for raw in fm_text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        # 顶层字段
        if not raw.startswith(" ") and ":" in line:
            key, _, val = line.partition(":")
            key = key.strip(); val = val.strip().strip("\"'")
            if key == "overrides":
                meta["overrides"] = {}
                in_overrides = True
                continue
            in_overrides = False
            meta[key] = _coerce(val)
        elif in_overrides and raw.startswith(" ") and ":" in line:
            key, _, val = line.lstrip().partition(":")
            meta["overrides"][key.strip()] = _coerce(val.strip().strip("\"'"))
    return meta, body


def _coerce(s: str):
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    if s.lower() in ("null", "none", "~"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def apply_overrides(manifest: dict, overrides: dict) -> dict:
    """点路径深度合并：'banner.max_width' -> manifest['banner']['max_width']."""
    for path, value in overrides.items():
        node = manifest
        parts = path.split(".")
        for p in parts[:-1]:
            if not isinstance(node.get(p), dict):
                node[p] = {}
            node = node[p]
        node[parts[-1]] = value
    return manifest


def validate_footer(md_text: str) -> None:
    """硬约束：互动板块出现后，版尾必须包含完整的 6 件套。

    顺序：互动 → banner（球场热闻标识）→ grid（推文卡）→ divider（红线）→
          带链接版尾图1 → 带链接版尾图2

    缺一项就 SystemExit，agent 必须补齐。允许改文案/图片，不允许缺失结构。
    """
    # 找互动板块结束位置，后续作为版尾区检查
    m = re.search(r":::\s*interact[\s\S]*?\n:::\s*\n", md_text)
    if not m:
        return  # 没有互动板块就不强制（可能是短稿）
    footer_md = md_text[m.end():]

    required = [
        ("banner", r":::\s*banner\s*\n", "装饰小 banner（如球场热闻标识）"),
        ("grid", r":::\s*grid\s*\n", "2x2 推文卡网格"),
        ("divider", r":::\s*divider\s*\n", "红色分割线"),
    ]
    missing: list[str] = []
    for key, pattern, desc in required:
        if not re.search(pattern, footer_md):
            missing.append(f"  - :::{key}::: → {desc}")

    # 引导动图 = 单独成段的图（带不带链接都算）。互动后至少要 2 张
    # 同时匹配 [![](img)](url) 和 ![](img) 两种写法
    linked_imgs = re.findall(r"\[!\[[^\]]*\]\([^\)]+\)\]\(https?://[^\)]+\)", footer_md)
    plain_imgs = re.findall(r"^\!\[[^\]]*\]\([^\)]+\)\s*$", footer_md, flags=re.MULTILINE)
    total_imgs = len(linked_imgs) + len(plain_imgs)
    if total_imgs < 2:
        missing.append(
            f"  - 引导动图 ×2 → ![alt](gif.gif) 写法（不带链接），互动后至少 2 张（找到 {total_imgs} 张）"
        )

    if missing:
        raise SystemExit(
            "[validate] 版尾结构不完整！互动板块开始后必须依次包含以下板块：\n"
            + "\n".join(missing)
            + "\n\n硬约束：允许改文案和图片，不允许缺失结构。完整顺序：\n"
            "  1. :::interact:::\n  2. :::banner::: (球场热闻标识)\n"
            "  3. :::grid::: (4 张推文卡，带链接)\n  4. :::divider:::\n"
            "  5. ![](引导动图1) （不带链接）\n  6. ![](引导动图2) （不带链接）\n"
            "\n参考 examples/edwards-sample.md"
        )


def render_markdown(md_text: str, theme: str, base_dir: Path) -> tuple[str, str]:
    """返回 (rendered_html_fragment, theme_actually_used)."""
    meta, body_md = parse_frontmatter(md_text)
    actual_theme = meta.get("theme", theme)
    validate_footer(body_md)
    manifest, env = load_theme(actual_theme)
    if "overrides" in meta:
        manifest = apply_overrides(manifest, meta["overrides"])
    md = MarkdownIt("commonmark", {"breaks": False, "html": True}).enable("strikethrough").enable("table")
    for name in ("interact", "grid", "divider", "center", "banner"):
        md.use(container_plugin, name=name)
    tokens = md.parse(body_md)
    body = render_blocks(tokens, manifest, env, base_dir)
    wrapper_style = manifest.get("article_wrapper_style", "")
    return f'<section style="{wrapper_style}">\n{body}\n</section>\n', actual_theme


def main():
    ap = argparse.ArgumentParser(description="Markdown → 公众号可粘贴 HTML")
    ap.add_argument("md_path", help="markdown 文件路径")
    ap.add_argument("--theme", default="edwards", help="主题名 (默认 edwards；frontmatter 里 theme: 字段会覆盖)")
    ap.add_argument("--output", "-o", help="输出 HTML 路径，默认与 md 同目录同名 .html")
    ap.add_argument("--no-open", action="store_true", help="不自动用浏览器打开")
    args = ap.parse_args()

    md_path = Path(args.md_path).expanduser().resolve()
    if not md_path.exists():
        raise SystemExit(f"markdown not found: {md_path}")

    md_text = md_path.read_text(encoding="utf-8")
    fragment, theme_used = render_markdown(md_text, args.theme, md_path.parent)

    # 包成完整 HTML 文档，方便浏览器直接打开看效果
    full = (
        "<!doctype html>\n<html><head><meta charset='utf-8'>"
        f"<title>{html.escape(md_path.stem)} (wechat preview)</title>"
        "<style>"
        "body{margin:0;padding:24px 0;background:#ececec;font-size:15px;}"
        ".paper{max-width:375px;margin:0 auto;background:#fff;padding:0;"
        "box-shadow:0 2px 8px rgba(0,0,0,.08);overflow:hidden;}"
        "#copy-btn{position:fixed;top:16px;right:16px;z-index:1000;"
        "padding:10px 18px;background:#07c160;color:#fff;border:0;"
        "border-radius:6px;font-size:14px;font-weight:bold;cursor:pointer;"
        "box-shadow:0 2px 8px rgba(0,0,0,.15);transition:all .15s;}"
        "#copy-btn:hover{background:#06ad55;transform:translateY(-1px);}"
        "#copy-btn:active{transform:translateY(0);}"
        "#copy-btn.success{background:#1976d2;}"
        "#copy-btn.error{background:#c62828;}"
        "#copy-tip{position:fixed;top:60px;right:16px;z-index:1000;"
        "max-width:240px;padding:10px 12px;background:#333;color:#fff;"
        "font-size:12px;border-radius:4px;line-height:1.5;display:none;}"
        "</style></head><body>"
        "<button id='copy-btn' type='button'>📋 复制到公众号</button>"
        "<div id='copy-tip'></div>"
        "<div class='paper'>\n"
        f"{fragment}"
        "\n</div>"
        + _COPY_SCRIPT +
        "</body></html>\n"
    )

    out_path = Path(args.output).expanduser().resolve() if args.output else md_path.with_suffix(".html")
    out_path.write_text(full, encoding="utf-8")
    print(f"[ok] 已生成 {out_path}  (theme={theme_used})")
    print("[tip] 在浏览器中点右上角'📋 复制到公众号'按钮，到 mp 后台 Ctrl+V 粘贴即可")

    if not args.no_open and sys.platform == "darwin":
        subprocess.Popen(["open", str(out_path)])
    elif not args.no_open and sys.platform.startswith("linux"):
        subprocess.Popen(["xdg-open", str(out_path)])


if __name__ == "__main__":
    main()
