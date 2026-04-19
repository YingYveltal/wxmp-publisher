"""图片处理：本地路径 → base64 data URI 内嵌。

公众号后台粘贴 base64 图片时，浏览器会自动把它当成普通 img 处理；
发布前微信会把所有 img src 转存到 mmbiz.qpic.cn，所以 base64 是离线生成最稳的姿势。
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

# 公众号后台对单图大小没有硬上限，但 base64 后体积膨胀 ~33%，
# 超过 5MB 的图建议用户压缩，否则粘贴时浏览器会卡。
WARN_BYTES = 5 * 1024 * 1024


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    if mime and mime.startswith("image/"):
        return mime
    suffix = path.suffix.lower().lstrip(".")
    return f"image/{suffix or 'png'}"


def to_data_uri(path: str | Path, base_dir: Path | None = None) -> str:
    """把本地图片读成 data:image/...;base64,xxx。

    - 相对路径基于 base_dir（通常是 markdown 文件所在目录）。
    - 已经是 http(s)://、data:、mmbiz.qpic.cn 的 URL 直接原样返回。
    """
    s = str(path).strip()
    if s.startswith(("http://", "https://", "data:")):
        return s

    p = Path(s)
    if not p.is_absolute() and base_dir is not None:
        p = (base_dir / p).resolve()

    if not p.exists():
        # 找不到就保留原 src，至少粘贴时还能看到一个红 X 提示用户
        return s

    raw = p.read_bytes()
    if len(raw) > WARN_BYTES:
        print(f"[warn] 图片 {p} 大小 {len(raw)/1024/1024:.1f}MB，建议压缩")

    mime = _guess_mime(p)
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"
