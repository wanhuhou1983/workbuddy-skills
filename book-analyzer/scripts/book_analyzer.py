#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
book_analyzer.py
================
读取一本书的完整文本，调用 DeepSeek API，输出：
  - 书籍概要（200-300字）
  - 核心主张 / 核心要求（10条）
  - 学术派系 / 思想谱系
  - 100 句金句

用法
----
  python3 book_analyzer.py <书籍文件路径> [选项]

选项
----
  --api-key   DeepSeek API Key（也可用环境变量 DEEPSEEK_API_KEY）
  --output    输出文件路径（默认：<书名>_analysis.md，与输入文件同目录）
  --model     DeepSeek 模型（默认：deepseek-chat，也可选 deepseek-reasoner）
  --chunk     单次提交的最大字符数（默认 60000；超出自动分块摘要后汇总）
  --encoding  文件编码（默认 utf-8）
  --preprocess  是否先修复 OCR 问题（标题层级、错误换行）（默认开启）

示例
----
  python3 book_analyzer.py ~/books/道德经.txt --api-key sk-xxx
  DEEPSEEK_API_KEY=sk-xxx python3 book_analyzer.py ~/books/资本论.md
  python3 book_analyzer.py ~/books/工业革命.md --preprocess  # 先修复 OCR
"""

import argparse
import json
import os
import sys
import time
import re
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("❌ 缺少 requests 库，请执行：pip3 install requests")

# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_CHUNK = 60_000       # 单块最大字符数（约 30k tokens）
MAX_RETRIES = 3
RETRY_WAIT = 5               # 重试等待秒数


# ──────────────────────────────────────────────
# DeepSeek 调用封装
# ──────────────────────────────────────────────
def call_deepseek(api_key: str, model: str, messages: list, temperature: float = 0.7) -> str:
    """调用 DeepSeek chat completion，返回回复文本。遇到限流自动重试。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
            elif resp.status_code == 429:
                wait = RETRY_WAIT * attempt
                print(f"  ⚠️  限流 (429)，{wait}s 后重试 ({attempt}/{MAX_RETRIES})...")
                time.sleep(wait)
            elif resp.status_code in (500, 502, 503):
                wait = RETRY_WAIT * attempt
                print(f"  ⚠️  服务器错误 ({resp.status_code})，{wait}s 后重试...")
                time.sleep(wait)
            else:
                resp.raise_for_status()
        except requests.exceptions.Timeout:
            print(f"  ⚠️  请求超时，重试 ({attempt}/{MAX_RETRIES})...")
            time.sleep(RETRY_WAIT)
        except requests.exceptions.ConnectionError as e:
            print(f"  ⚠️  网络连接错误: {e}，重试 ({attempt}/{MAX_RETRIES})...")
            time.sleep(RETRY_WAIT)

    sys.exit("❌ DeepSeek API 多次失败，请检查网络或 API Key")


# ──────────────────────────────────────────────
# OCR 预处理：修复标题层级（只处理标题，不处理正文）
# ──────────────────────────────────────────────
def extract_headings(lines: list) -> list:
    """提取所有标题行及其位置"""
    headings = []
    for i, line in enumerate(lines):
        if line.strip().startswith('#'):
            headings.append((i, line.strip()))
    return headings

def call_llm_fix_headings(headings_text: str, api_key: str, model: str) -> str:
    """调用 LLM 分析标题层级（只处理标题，不处理正文）"""
    prompt = """你是书籍结构分析专家。请分析以下书籍标题的层级结构。

根据书籍结构规范，判断每个标题的级别：
- 书籍封面标题 → H1
- "序"、"总序"、"前言"、"引言"、"卷首语"、"致谢"、"后记"、"译后记" → H1
- "第X章" → H1
- "第一篇"、"第二篇" → H1
- 章节名（如"对工业革命进程的解释"、"社会结构的变动"）→ H2
- 章节内的主要论点标题 → H3
- 更细分的论点 → H4 或正文

输出格式（严格按此格式，每行一个）：
H1 标题内容
H2 标题内容
H3 标题内容
...

只输出标题和级别，不要其他内容。
"""
    messages = [
        {"role": "system", "content": "你是书籍结构分析专家。"},
        {"role": "user", "content": f"{prompt}\n\n{headings_text}"}
    ]
    result = call_deepseek(api_key, model, messages, temperature=0.1)
    return result

def parse_llm_result(llm_result: str) -> dict:
    """解析 LLM 返回的标题层级"""
    import re
    level_map = {}
    for line in llm_result.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        m = re.match(r'^(H[1-6])[:\s]+(.+)', line, re.IGNORECASE)
        if m:
            level = int(m.group(1)[1])
            title = m.group(2).strip()
            level_map[title] = level
    return level_map

def apply_heading_levels(lines: list, level_map: dict) -> list:
    """应用标题层级到原文"""
    import re
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#'):
            content = stripped.lstrip('#').lstrip()
            level = None
            for title, lvl in level_map.items():
                if content == title or title in content or content in title:
                    level = lvl
                    break
            if level:
                hashes = '#' * level
                result.append(f"{hashes} {content}")
            else:
                result.append(line)
        else:
            result.append(line)
    return result

def preprocess_ocr(text: str, api_key: str, model: str) -> str:
    """OCR 预处理：只修复标题层级，不处理正文（避免内容压缩）"""
    print("  🔧 检测到 OCR 书籍，修复标题层级...")
    
    lines = text.split('\n')
    headings = extract_headings(lines)
    
    if not headings:
        print("  ℹ️  未找到标题，跳过预处理")
        return text
    
    # 检查是否所有标题都是 H1
    h1_count = sum(1 for _, h in headings if h.startswith('# ') and not h.startswith('## '))
    if h1_count < len(headings) * 0.8:
        print("  ℹ️  标题层级可能已经正确，跳过预处理")
        return text
    
    print(f"  发现 {len(headings)} 个标题，调用 LLM 分析层级...")
    
    # 提取标题文本
    headings_text = '\n'.join([h[1] for _, h in headings])
    
    # 调用 LLM
    llm_result = call_llm_fix_headings(headings_text, api_key, model)
    if not llm_result:
        print("  ⚠️  LLM 调用失败，跳过预处理")
        return text
    
    # 解析并应用
    level_map = parse_llm_result(llm_result)
    print(f"  识别了 {len(level_map)} 个标题层级")
    result_lines = apply_heading_levels(lines, level_map)
    
    print("  ✅ 标题层级修复完成")
    return '\n'.join(result_lines)


# ──────────────────────────────────────────────
# 文本分块工具（按章节分块）
# ──────────────────────────────────────────────
def split_by_headings(text: str) -> list[dict]:
    """
    按 H1 标题分块，返回块列表。
    每块包含：heading（标题）、content（内容）、level（层级）
    """
    import re
    lines = text.split('\n')
    blocks = []
    current_block = {"heading": "", "content": [], "level": 1}
    
    for line in lines:
        stripped = line.strip()
        # 检测标题行
        m = re.match(r'^(#{1,6})\s+(.+?)\s*$', stripped)
        if m:
            hashes = m.group(1)
            level = len(hashes)
            title = m.group(2).strip()
            
            # 如果是 H1，先保存当前块
            if level == 1 and current_block["content"]:
                blocks.append(current_block)
                current_block = {"heading": title, "content": [], "level": level}
            else:
                # 保存之前的块内容（如果有的话）
                if current_block["heading"] or current_block["content"]:
                    blocks.append(current_block)
                current_block = {"heading": title, "content": [], "level": level}
        else:
            current_block["content"].append(line)
    
    # 最后一个块
    if current_block["content"]:
        blocks.append(current_block)
    
    return blocks


def split_text(text: str, chunk_size: int) -> list[str]:
    """按 chunk_size 字符分割文本，尽量在段落处断开。"""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:])
            break
        # 尝试在段落换行处断开
        cut = text.rfind("\n\n", start, end)
        if cut == -1 or cut <= start:
            cut = text.rfind("\n", start, end)
        if cut == -1 or cut <= start:
            cut = end
        chunks.append(text[start:cut])
        start = cut
    return chunks


def fix_heading_in_chunk(chunk_heading: str, chunk_content: str, all_headings: list, api_key: str, model: str) -> str:
    """
    修复单个章节的标题层级。
    传入完整标题列表，让 LLM 判断当前章节的正确层级。
    """
    # 构建完整的章节结构（用于上下文）
    toc = "\n".join([f"{'#' * h['level']} {h['heading']}" for h in all_headings[:30]])  # 最多30个标题
    
    prompt = f"""你是书籍结构分析专家。以下是一本书的章节结构（部分）：

```
{toc}
```

请分析当前章节「{chunk_heading}」的标题级别。

规则：
- "序"、"总序"、"前言"、"引言"、"卷首语"、"致谢"、"后记" → 1（保持H1）
- "第X章"、"第一篇"、"第二篇" → 1（H1）
- 主要章节名（如"对工业革命进程的解释"）→ 2（H2）
- 章节内论点标题 → 3（H3）或更深

请只输出级别数字（1-6），不要其他内容。"""
    
    messages = [
        {"role": "system", "content": "你是书籍结构分析专家。"},
        {"role": "user", "content": prompt}
    ]
    
    result = call_deepseek(api_key, model, messages, temperature=0.1)
    
    # 解析结果
    import re
    m = re.search(r'\b([1-6])\b', result.strip())
    if m:
        return int(m.group(1))
    return 1  # 默认 H1


# ──────────────────────────────────────────────
# 多块摘要 → 汇总（按章节分块）
# ──────────────────────────────────────────────
def summarize_by_chapters(api_key: str, model: str, blocks: list[dict], book_title: str) -> dict:
    """
    按章节分块摘要，每块包含完整章节结构上下文。
    返回：{"summaries": [...], "quotes": [...], "heading_fixes": {...}}
    """
    total = len(blocks)
    print(f"  📦 书籍已分为 {total} 个章节，逐块分析中...")
    
    summaries = []
    all_quotes = []
    heading_fixes = {}
    
    for i, block in enumerate(blocks, 1):
        heading = block["heading"]
        content = "\n".join(block["content"])
        level = block["level"]
        
        # 构建完整章节结构（上下文）
        toc = "\n".join([
            f"{'#' * b['level']} {b['heading']}" 
            for b in blocks[max(0, i-5):min(len(blocks), i+5)]  # 前后各5个章节
        ])
        
        # 检测是否需要修复标题层级
        needs_fix = level == 1 and heading  # 当前是 H1 且有标题
        fix_hint = ""
        if needs_fix:
            fix_hint = f"\n\n【重要】请根据以下章节结构，判断「{heading}」的正确标题级别：\n{toc}\n只输出级别数字1-6。"
        
        print(f"    📖 第 {i}/{total} 章：{heading or '(无标题)'}...")
        
        msgs = [
            {
                "role": "system",
                "content": (
                    "你是一位专业的书籍分析师。你的任务是：\n"
                    "1. 对书籍章节进行精炼摘要\n"
                    "2. 提取该章节中的精彩语句\n"
                    f"3. 【仅当存在fix_hint时】根据章节结构判断标题级别\n\n"
                    "请用中文输出。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"以下是《{book_title}》第 {i}/{total} 章的内容。\n\n"
                    f"【章节结构上下文（前后章节）】\n{toc}\n\n"
                    f"【本章标题】{heading or '（无标题）'}\n\n"
                    f"【本章内容】\n{content[:8000]}"  # 限制单块大小
                    f"{fix_hint}"
                ),
            },
        ]
        
        result = call_deepseek(api_key, model, msgs, temperature=0.5)
        
        # 解析结果
        if fix_hint and result.strip()[-1] in '123456':
            # LLM 可能把级别数字放在最后
            try:
                new_level = int(result.strip()[-1])
                heading_fixes[heading] = new_level
                print(f"      → 标题层级: H{new_level}")
            except:
                pass
        
        # 提取摘要（去掉可能的级别数字）
        summary = re.sub(r'^[123456]\s*$', '', result.strip(), flags=re.MULTILINE).strip()
        summaries.append(f"=== 第 {i} 章「{heading}」摘要 ===\n{summary}")
    
    print("  🔗 汇总各章节分析...")
    return {
        "summaries": summaries,
        "quotes": all_quotes,
        "heading_fixes": heading_fixes
    }


# ──────────────────────────────────────────────
# 核心分析 Prompt
# ──────────────────────────────────────────────
SYSTEM_PROMPT = """你是一位顶级的书籍分析专家，兼具文学批评、哲学、社会科学、经济学等跨学科素养。
你的任务是对所给书籍进行深度分析，输出结构严谨、内容精准的 Markdown 报告。
请用中文输出，行文流畅、专业、有见地。"""

ANALYSIS_PROMPT_TEMPLATE = """请对《{title}》进行全面深度分析，严格按照以下 Markdown 结构输出，不要省略任何部分：

---

# 《{title}》深度分析报告

## 一、书籍概要

（200-300字。涵盖：成书背景、作者立场、核心议题、主要结构、写作风格）

## 二、核心主张与要求

（共10条，每条独立成段，格式：**主张X**：内容说明）

## 三、学术派系与思想谱系

（300字左右。说明：
- 本书归属哪个/哪几个学术流派或思想传统
- 与哪些经典理论、学派的继承/对话/批判关系
- 在学术史上的位置与影响）

## 四、100句金句

（每行一句，格式：`序号. "金句原文"` — 简短来源或语境注释（可选））
（金句要求：忠实原文精神、涵盖全书各章、兼顾深度与可读性）

---

{content_label}：

{content}
"""


def build_analysis_prompt(title: str, content: str, is_summary: bool = False) -> str:
    label = "【各章节摘要（书籍超长已预处理）】" if is_summary else "【书籍全文】"
    return ANALYSIS_PROMPT_TEMPLATE.format(
        title=title,
        content_label=label,
        content=content,
    )


# ──────────────────────────────────────────────
# 主分析流程（按章节分块 + 同步修复标题）
# ──────────────────────────────────────────────
def analyze_book(api_key: str, model: str, text: str, title: str, chunk_size: int, need_preprocess: bool = False) -> tuple[str, dict]:
    """
    完整分析流程，返回 (报告字符串, 标题修复映射)。
    按章节分块分析，同步修复标题层级。
    """
    # 按章节分块
    blocks = split_by_headings(text)
    
    print(f"  📚 检测到 {len(blocks)} 个章节")
    
    if len(blocks) <= 3:
        # 章节少，直接全文分析
        print("  📖 章节较少，直接全文分析...")
        content_for_analysis = text
        is_summary = False
        heading_fixes = {}
    else:
        # 章节多，按章节分块分析
        print("  📦 章节较多，按章节分块深度分析...")
        chapter_result = summarize_by_chapters(api_key, model, blocks, title)
        content_for_analysis = "\n\n".join(chapter_result["summaries"])
        is_summary = True
        heading_fixes = chapter_result["heading_fixes"]

    print("  🤖 调用 DeepSeek 进行深度分析（可能需要 30-120 秒）...")
    user_prompt = build_analysis_prompt(title, content_for_analysis, is_summary)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    result = call_deepseek(api_key, model, messages, temperature=0.7)
    return result, heading_fixes


# ──────────────────────────────────────────────
# 输出后处理：确保100句金句完整
# ──────────────────────────────────────────────
def count_quotes(report: str) -> int:
    """统计报告中金句数量（匹配"数字. "行）。"""
    section_match = re.search(r"## 四、100句金句(.*?)(?=^##|\Z)", report, re.DOTALL | re.MULTILINE)
    if not section_match:
        return 0
    section = section_match.group(1)
    return len(re.findall(r"^\s*\d+\.", section, re.MULTILINE))


def supplement_quotes(api_key: str, model: str, report: str, title: str, current_count: int) -> str:
    """如果金句不足100条，补充至100条。"""
    needed = 100 - current_count
    if needed <= 0:
        return report

    print(f"  📝 金句仅 {current_count} 条，补充 {needed} 条...")
    msgs = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"以下是《{title}》的分析报告（包含已有的 {current_count} 句金句）。\n"
                f"请再补充 {needed} 句金句，序号从 {current_count + 1} 开始，"
                f"格式与原有一致：`序号. '金句原文'`\n"
                f"不要重复已有金句，要忠实于原书精神。\n\n"
                f"仅输出新增金句列表，不要重复报告其他部分。"
            ),
        },
    ]
    supplement = call_deepseek(api_key, model, msgs, temperature=0.7)

    # 将补充金句插入报告末尾（四、章节之后）
    insert_point = report.rfind("\n---")
    if insert_point == -1:
        return report + "\n\n" + supplement
    return report[:insert_point] + "\n\n" + supplement + report[insert_point:]


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="调用 DeepSeek 对书籍全文进行深度分析",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", help="书籍文件路径（.txt / .md / .text）")
    parser.add_argument("--api-key", default=os.environ.get("DEEPSEEK_API_KEY", ""), help="DeepSeek API Key")
    parser.add_argument("--output", default="", help="输出 Markdown 文件路径（默认同目录下 <书名>_analysis.md）")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"DeepSeek 模型（默认：{DEFAULT_MODEL}）")
    parser.add_argument("--chunk", type=int, default=DEFAULT_CHUNK, help=f"分块字符数（默认：{DEFAULT_CHUNK}）")
    parser.add_argument("--encoding", default="utf-8", help="文件编码（默认：utf-8）")
    parser.add_argument("--title", default="", help="手动指定书名（默认从文件名推断）")
    parser.add_argument("--no-supplement", action="store_true", help="不自动补充至100句金句")
    parser.add_argument("--preprocess", action="store_true", default=True, help="分析前先修复 OCR 问题（默认开启）")
    parser.add_argument("--no-preprocess", action="store_true", help="跳过 OCR 预处理步骤")
    return parser.parse_args()


def infer_title(filepath: str) -> str:
    """从文件名推断书名（去掉扩展名和常见后缀）。"""
    name = Path(filepath).stem
    # 去掉常见的"每天听本书_"前缀等
    name = re.sub(r"^(每天听本书[_\-\s]*|【每天听本书】)", "", name).strip()
    return name or "未知书名"


def main():
    args = parse_args()

    # ── API Key 检查
    if not args.api_key:
        sys.exit(
            "❌ 未提供 DeepSeek API Key。\n"
            "   方式1：--api-key sk-xxx\n"
            "   方式2：export DEEPSEEK_API_KEY=sk-xxx"
        )

    # ── 读取书籍文件
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        sys.exit(f"❌ 文件不存在：{input_path}")

    print(f"📚 读取文件：{input_path}")
    try:
        text = input_path.read_text(encoding=args.encoding, errors="replace")
    except Exception as e:
        sys.exit(f"❌ 读取失败：{e}")

    text = text.strip()
    char_count = len(text)
    print(f"   字符数：{char_count:,}（约 {char_count // 2:,} tokens）")

    if char_count < 100:
        sys.exit("❌ 文件内容过少（< 100字），请检查文件路径和编码")

    # ── OCR 预处理（可选）
    if not args.no_preprocess:
        text = preprocess_ocr(text, args.api_key, args.model)

    # ── 书名
    title = args.title.strip() or infer_title(str(input_path))
    print(f"   书名：《{title}》")

    # ── 输出路径
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        output_path = input_path.parent / f"{title}_analysis.md"

    # ── 分析（按章节分块 + 同步修复标题）
    print(f"\n🔍 开始分析《{title}》...")
    report, heading_fixes = analyze_book(args.api_key, args.model, text, title, args.chunk)
    
    # 显示标题修复信息
    if heading_fixes:
        print("  📌 标题层级修复：")
        for heading, level in heading_fixes.items():
            print(f"     「{heading}」→ H{level}")

    # ── 检查金句数量，按需补充
    if not args.no_supplement:
        q_count = count_quotes(report)
        print(f"   ✅ 金句计数：{q_count} 句")
        if q_count < 95:  # 允许95-100句均视为合格
            report = supplement_quotes(args.api_key, args.model, report, title, q_count)

    # ── 写入输出文件
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"\n✅ 分析完成！报告已保存至：\n   {output_path}")

    # ── 打印摘要预览
    preview_lines = report.split("\n")[:20]
    print("\n─── 报告预览（前20行）─────────────────────────")
    print("\n".join(preview_lines))
    print("─" * 50)


if __name__ == "__main__":
    main()
