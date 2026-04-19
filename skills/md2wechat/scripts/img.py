"""图片处理：本地路径 → base64 data URI 内嵌。

公众号后台粘贴 base64 图片时，浏览器会自动把它当成普通 img 处理；
发布前微信会把所有 img src 转存到 mmbiz.qpic.cn，所以 base64 是离线生成最稳的姿势。

⚠ **粘贴到公众号编辑器的单图硬上限是 5MB**（PNG/JPG/GIF 都一样）。
即使图本身是 6MB 的 GIF，粘贴时也会报"载入失败、来源信息无法识别"。
（素材库上传支持 10MB，但粘贴通道 5MB 是公众号后台的硬限制，详见 README FAQ。）
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

# 公众号粘贴通道单图硬上限。超过会被公众号编辑器拒绝。
MAX_BYTES = 5 * 1024 * 1024


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
    - 单图超过 5MB 直接 SystemExit，因为粘贴公众号会失败。
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
    if len(raw) > MAX_BYTES:
        size_mb = len(raw) / 1024 / 1024
        raise SystemExit(
            f"\n[image-size] 图片 {p} 太大（{size_mb:.1f}MB），超过公众号粘贴 5MB 上限。\n"
            f"\n粘贴失败的具体表现：保存时提示'载入失败、来源信息无法识别'。\n"
            f"\n解决方法（任选一）：\n"
            f"  1. 用 ezgif.com / squoosh.app 压缩到 5MB 以下\n"
            f"  2. GIF 减帧或缩短时长\n"
            f"  3. PNG/JPG 降低分辨率或质量\n"
            f"  4. 大图先手工上传到公众号素材库（支持 10MB），从素材库插入到正文（脱离 base64 流程）\n"
        )

    mime = _guess_mime(p)
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"

