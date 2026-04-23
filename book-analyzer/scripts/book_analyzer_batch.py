#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
book_analyzer_batch.py
======================
批量调用 book_analyzer.py，对目录下所有书籍文件进行分析。

用法
----
  python3 book_analyzer_batch.py <书籍目录> [选项]

选项
----
  --api-key       DeepSeek API Key（也可用 DEEPSEEK_API_KEY 环境变量）
  --output-dir    输出目录（默认：<书籍目录>/analysis_output/）
  --ext           文件扩展名，逗号分隔（默认：txt,md）
  --model         DeepSeek 模型（默认：deepseek-chat）
  --chunk         分块字符数（默认：60000）
  --interval      每本书之间等待秒数，避免限流（默认：3）
  --skip-exists   跳过已有输出文件的书籍
  --glob          文件匹配 glob（覆盖 --ext，如 '*.txt'）

示例
----
  python3 book_analyzer_batch.py ~/books/ --api-key sk-xxx --skip-exists
  DEEPSEEK_API_KEY=sk-xxx python3 book_analyzer_batch.py ~/books/ --interval 5
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="批量书籍分析（调用 book_analyzer.py）")
    parser.add_argument("directory", help="书籍文件所在目录")
    parser.add_argument("--api-key", default=os.environ.get("DEEPSEEK_API_KEY", ""))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--ext", default="txt,md", help="文件扩展名（逗号分隔，默认 txt,md）")
    parser.add_argument("--glob", default="", help="文件 glob（优先级高于 --ext）")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--chunk", type=int, default=60000)
    parser.add_argument("--interval", type=float, default=3.0, help="每本书之间等待秒数")
    parser.add_argument("--skip-exists", action="store_true", help="跳过已存在的输出文件")
    parser.add_argument("--no-supplement", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.api_key:
        sys.exit("❌ 未提供 API Key。使用 --api-key 或 export DEEPSEEK_API_KEY=sk-xxx")

    book_dir = Path(args.directory).expanduser().resolve()
    if not book_dir.is_dir():
        sys.exit(f"❌ 目录不存在：{book_dir}")

    out_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else book_dir / "analysis_output"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 收集文件
    if args.glob:
        files = sorted(book_dir.glob(args.glob))
    else:
        exts = [e.strip().lstrip(".") for e in args.ext.split(",")]
        files = []
        for ext in exts:
            files.extend(book_dir.glob(f"*.{ext}"))
        files = sorted(set(files))

    if not files:
        sys.exit(f"❌ 目录 {book_dir} 下未找到匹配文件（ext={args.ext}）")

    print(f"📚 共找到 {len(files)} 本书籍，输出至：{out_dir}\n")

    analyzer_script = Path(__file__).parent / "book_analyzer.py"
    success, skipped, failed = 0, 0, []

    for i, fpath in enumerate(files, 1):
        title_stem = fpath.stem
        out_file = out_dir / f"{title_stem}_analysis.md"

        if args.skip_exists and out_file.exists():
            print(f"[{i:3d}/{len(files)}] ⏩ 已跳过（已存在）：{fpath.name}")
            skipped += 1
            continue

        print(f"[{i:3d}/{len(files)}] 📖 分析中：{fpath.name}")

        cmd = [
            sys.executable, str(analyzer_script),
            str(fpath),
            "--api-key", args.api_key,
            "--output", str(out_file),
            "--model", args.model,
            "--chunk", str(args.chunk),
        ]
        if args.no_supplement:
            cmd.append("--no-supplement")

        result = subprocess.run(cmd, capture_output=False, text=True)

        if result.returncode == 0:
            print(f"   ✅ 完成：{out_file.name}\n")
            success += 1
        else:
            print(f"   ❌ 失败（exit {result.returncode}）\n")
            failed.append(fpath.name)

        if i < len(files):
            time.sleep(args.interval)

    print("=" * 50)
    print(f"📊 批量分析完成：成功 {success} / 跳过 {skipped} / 失败 {len(failed)}")
    if failed:
        print("❌ 失败列表：")
        for f in failed:
            print(f"   - {f}")


if __name__ == "__main__":
    main()
