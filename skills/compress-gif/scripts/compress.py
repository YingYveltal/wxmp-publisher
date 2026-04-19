"""GIF 智能压缩到指定大小。

公众号粘贴单图硬上限 5MB，超过会保存失败"载入失败、来源信息无法识别"。
本工具用 gifsicle（业界 GIF 优化标准）多步降级直到达标：

  Step 1: --optimize=3 无损优化（重排调色板 + 删冗余像素）
  Step 2: --colors N 减色（256 → 128 → 64 → 32）
  Step 3: --scale R 缩放（0.9 → 0.8 → 0.7 → 0.5）
  Step 4: --lossy=N 有损压缩（80 → 120 → 200）
  Step 5: 抽帧（每 N 帧保留 1 帧）

每步压完测大小，达标即停。前面的步骤先做，效果不够再加后面的。

依赖: gifsicle（macOS: brew install gifsicle，Linux: apt-get install gifsicle）
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_TARGET_BYTES = 5 * 1024 * 1024  # 公众号粘贴 5MB 硬上限


def check_gifsicle() -> str:
    """检查 gifsicle 是否安装，返回路径。否则给出安装提示并退出。"""
    path = shutil.which("gifsicle")
    if not path:
        raise SystemExit(
            "[error] gifsicle 未安装。\n"
            "  macOS: brew install gifsicle\n"
            "  Linux: sudo apt-get install gifsicle  /  sudo yum install gifsicle\n"
        )
    return path


def file_size(path: Path) -> int:
    return path.stat().st_size


def fmt_size(n: int) -> str:
    return f"{n/1024/1024:.2f}MB" if n > 1024 * 1024 else f"{n/1024:.0f}KB"


def get_frame_count(path: Path) -> int:
    """用 gifsicle --info 数帧数。"""
    try:
        out = subprocess.check_output(["gifsicle", "--info", str(path)], stderr=subprocess.DEVNULL).decode()
        # 输出含 "X images"
        for line in out.splitlines():
            if "image" in line.lower():
                # 行形如 "  + image #0 ..." 不是；找 "X images" 在头部
                pass
        # 简单方法：count "image #" 出现次数
        return out.count("image #")
    except Exception:
        return 0


def run(cmd: list[str]) -> bool:
    """跑 gifsicle 命令，成功返回 True。"""
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False


def compress(input_path: Path, output_path: Path, target_bytes: int = DEFAULT_TARGET_BYTES,
             verbose: bool = True) -> dict:
    """多步降级压缩。返回 {'original': bytes, 'final': bytes, 'steps': [...]}"""
    check_gifsicle()
    if not input_path.exists():
        raise SystemExit(f"输入不存在: {input_path}")

    orig_size = file_size(input_path)
    steps: list[dict] = []

    def log(msg: str):
        if verbose:
            print(msg)

    log(f"[input] {input_path.name} {fmt_size(orig_size)}")

    if orig_size <= target_bytes:
        # 已经达标，直接拷贝
        shutil.copy(input_path, output_path)
        log(f"[ok] 已小于目标 {fmt_size(target_bytes)}，直接拷贝")
        return {"original": orig_size, "final": orig_size, "steps": [], "needed_compression": False}

    # Step 1: 无损优化
    log(f"\n[step 1] gifsicle --optimize=3 无损优化")
    if run(["gifsicle", "--optimize=3", str(input_path), "-o", str(output_path)]):
        sz = file_size(output_path)
        steps.append({"step": "optimize=3", "size": sz})
        log(f"  → {fmt_size(sz)} ({(1-sz/orig_size)*100:.0f}% 减小)")
        if sz <= target_bytes:
            return _result(orig_size, sz, steps)

    src = output_path  # 后续步骤在前一步基础上叠加
    # Step 2: 减色
    for colors in (256, 128, 64, 32):
        log(f"\n[step 2] --colors {colors}")
        if run(["gifsicle", "--optimize=3", f"--colors={colors}", str(src), "-o", str(output_path)]):
            sz = file_size(output_path)
            steps.append({"step": f"colors={colors}", "size": sz})
            log(f"  → {fmt_size(sz)} ({(1-sz/orig_size)*100:.0f}% 减小)")
            if sz <= target_bytes:
                return _result(orig_size, sz, steps)
            src = output_path

    # Step 3: 缩放
    for scale in (0.9, 0.8, 0.7, 0.5):
        log(f"\n[step 3] --scale {scale}")
        if run(["gifsicle", "--optimize=3", "--colors=64", f"--scale={scale}",
                str(input_path), "-o", str(output_path)]):
            sz = file_size(output_path)
            steps.append({"step": f"scale={scale}", "size": sz})
            log(f"  → {fmt_size(sz)} ({(1-sz/orig_size)*100:.0f}% 减小)")
            if sz <= target_bytes:
                return _result(orig_size, sz, steps)

    # Step 4: 有损压缩
    for lossy in (80, 120, 200):
        log(f"\n[step 4] --lossy={lossy}")
        if run(["gifsicle", "--optimize=3", "--colors=64", "--scale=0.7",
                f"--lossy={lossy}", str(input_path), "-o", str(output_path)]):
            sz = file_size(output_path)
            steps.append({"step": f"lossy={lossy}", "size": sz})
            log(f"  → {fmt_size(sz)} ({(1-sz/orig_size)*100:.0f}% 减小)")
            if sz <= target_bytes:
                return _result(orig_size, sz, steps)

    # Step 5: 抽帧（每 2/3/4 帧取 1）
    frames = get_frame_count(input_path)
    log(f"\n[info] 原 GIF 共 {frames} 帧，开始抽帧")
    for keep_every in (2, 3, 4, 5):
        # gifsicle 用 #0 #2 #4 形式选帧
        if frames > 0:
            keep_indices = list(range(0, frames, keep_every))
            sel = " ".join(f"#{i}" for i in keep_indices)
            log(f"\n[step 5] 每 {keep_every} 帧保留 1（{len(keep_indices)} 帧）")
            cmd = ["gifsicle", "--optimize=3", "--colors=64", "--scale=0.7", "--lossy=200"]
            cmd += sel.split() + [str(input_path), "-o", str(output_path)]
            if run(cmd):
                sz = file_size(output_path)
                steps.append({"step": f"keep-every-{keep_every} ({len(keep_indices)} frames)", "size": sz})
                log(f"  → {fmt_size(sz)} ({(1-sz/orig_size)*100:.0f}% 减小)")
                if sz <= target_bytes:
                    return _result(orig_size, sz, steps)

    # 所有步骤都没达标
    final_size = file_size(output_path)
    log(f"\n[warn] 所有降级策略后仍 {fmt_size(final_size)} > 目标 {fmt_size(target_bytes)}")
    log(f"       建议手工进一步处理：减少时长 / 用 ffmpeg 转 webp / 重新设计动画")
    return _result(orig_size, final_size, steps, success=False)


def _result(orig: int, final: int, steps: list, success: bool = True) -> dict:
    return {
        "original": orig,
        "final": final,
        "ratio": (1 - final / orig) if orig else 0,
        "steps": steps,
        "success": success,
        "needed_compression": True,
    }


def main():
    ap = argparse.ArgumentParser(description="GIF 智能压缩到指定大小（默认 5MB，公众号上限）")
    ap.add_argument("input", help="输入 GIF 路径")
    ap.add_argument("-o", "--output", help="输出路径，默认 <input>.compressed.gif")
    ap.add_argument("--target-mb", type=float, default=5.0,
                    help="目标大小（MB），默认 5（公众号上限）")
    ap.add_argument("--quiet", action="store_true", help="静默模式")
    args = ap.parse_args()

    inp = Path(args.input).expanduser().resolve()
    if not inp.exists():
        raise SystemExit(f"输入不存在: {inp}")
    if args.output:
        out = Path(args.output).expanduser().resolve()
    else:
        out = inp.with_suffix(".compressed.gif")
    target = int(args.target_mb * 1024 * 1024)

    result = compress(inp, out, target_bytes=target, verbose=not args.quiet)
    print(f"\n[done] {inp.name} {fmt_size(result['original'])} → {out.name} {fmt_size(result['final'])}")
    print(f"       压缩 {result['ratio']*100:.0f}%，{'达标' if result['final'] <= target else '未达标'}")
    print(f"       输出: {out}")
    if not result["success"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
