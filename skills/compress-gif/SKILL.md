---
name: compress-gif
description: GIF 智能压缩到指定大小（默认 5MB，公众号粘贴上限）。多步降级：无损优化 → 减色 → 缩放 → 有损 → 抽帧，达标即停
version: 1.0.0
platforms: [macos, linux]
metadata:
  hermes:
    tags: [gif, image, compression, wechat]
    category: media
    requires_toolsets: [terminal]
    composes_with: [md2wechat, text2md]
---

# compress-gif

把超大 GIF 智能压缩到指定大小（默认 5MB，公众号粘贴硬上限）。基于 [gifsicle](https://www.lcdf.org/gifsicle/)（业界 GIF 优化标准）。

## When to Use

- `text2md fill` 报错"图片 X.X MB 超过公众号粘贴 5MB 上限"
- 任何场景需要把 GIF 压到指定大小
- 配合 md2wechat / text2md 使用，自动解决"GIF 太大"问题

## How It Works

逐步降级，每步压缩后检测大小，达标即停（不会过度压缩）：

```
Step 1: --optimize=3       无损优化（重排调色板 + 删冗余像素）
Step 2: --colors N         减色 256 → 128 → 64 → 32
Step 3: --scale R          缩放 0.9 → 0.8 → 0.7 → 0.5
Step 4: --lossy=N          有损压缩 80 → 120 → 200
Step 5: 抽帧               每 2/3/4/5 帧保留 1 帧
```

前面的步骤先做，效果不够再加后面的。所以**视觉质量损失最小**。

## Usage

```bash
python3 ~/.hermes/skills/compress-gif/scripts/compress.py <input.gif> [-o output.gif] [--target-mb 5]
```

参数：
- `input` (位置参数)：源 GIF 路径
- `-o` / `--output`：输出路径，默认 `<input>.compressed.gif`
- `--target-mb`：目标大小 MB，默认 5（公众号上限）
- `--quiet`：静默模式，不打印每步进度

## 示例

```bash
# 把 9.3MB 的引导动图压到 5MB 以下
python3 ~/.hermes/skills/compress-gif/scripts/compress.py \
  ~/wxmp-articles/<workspace>/images/guide-2.gif \
  -o ~/wxmp-articles/<workspace>/images/guide-2.gif

# 输出（典型）：
# [input] guide-2.gif 9.30MB
# [step 1] gifsicle --optimize=3 无损优化
#   → 7.50MB (19% 减小)
# [step 2] --colors 128
#   → 4.80MB (48% 减小)
# [done] guide-2.gif 9.30MB → guide-2.compressed.gif 4.80MB
```

## 与 wxmp-publisher 配合

`text2md fill` 报"图片超过 5MB"时，agent 工作流：

1. 调 `compress-gif` 把对应图压缩到位
2. 把压缩后的文件覆盖原 file 路径，或者更新 `images.json` 的 `file` 字段指向新路径
3. 重跑 `text2md fill`

也可以提前对 images/ 下所有 GIF 做一遍：

```bash
for f in <workspace>/images/*.gif; do
  python3 ~/.hermes/skills/compress-gif/scripts/compress.py "$f" -o "$f"
done
```

（覆盖原文件，节省空间）

## 依赖

- **gifsicle**：业界 GIF 优化标准
  - macOS: `brew install gifsicle`
  - Linux: `sudo apt-get install gifsicle` 或 `sudo yum install gifsicle`

如未安装，运行时会给出明确提示。

## 限制 / 已知问题

- 对**极复杂的高色彩 GIF**（比如真人摄影类），减色后视觉损失可能明显，建议手工调
- 对**大量帧 + 大尺寸**的 GIF（如 200+ 帧 1920x1080），全套降级仍可能不够 5MB——会输出最后一步结果并 exit code 2，提示需手工处理
- 不支持 WebP / APNG（仅 GIF）。如有需求扩展可加 ffmpeg 备选

## 退出码

- `0`：成功，达标
- `2`：所有降级步骤后仍未达标（输出文件存在，但比目标大）
- 非零：其他错误（输入不存在、gifsicle 未装等）
