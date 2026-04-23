---
name: "book-analyzer"
slug: "book-analyzer"
version: "1.1.0"
description: "调用 DeepSeek API 对书籍全文进行深度分析，输出概要、核心主张、学术派系与100句金句。支持 OCR 书籍自动修复（按章节分块同步修复标题层级）。触发词：分析书籍、书籍分析、全文分析、生成金句、读书报告、学术派系、核心主张、书籍概要、OCR书籍分析、深度分析、书评报告。"
metadata: {"clawdbot":{"emoji":"📖","os":["linux","darwin","win32"],"requires":{"bins":["python3"]}}}
---

<objective>
读取书籍全文（.txt / .md 格式），调用 DeepSeek Chat API，生成结构化深度分析报告，包含：
1. 书籍概要（200-300字）
2. 核心主张与要求（10条）
3. 学术派系与思想谱系
4. 100句金句
</objective>

<use_when>
- 用户提到要"分析书籍"、"书籍分析"、"全文分析"、"生成金句"
- 用户提到"读书报告"、"书评"、"深度分析"
- 用户提供了书籍文件路径（.txt / .md）并要求分析
- 用户说"分析这本书"、"帮我看看这本书"并附有文件路径
- 用户提到"学术派系"、"核心主张"、"书籍概要"、"100句金句"
- 用户有 OCR 扫描书籍需要批量分析
</use_when>

<config>
- **脚本目录**：`~/.workbuddy/skills/book-analyzer/scripts/`
- **单本分析脚本**：`scripts/book_analyzer.py`
- **批量分析脚本**：`scripts/book_analyzer_batch.py`
- **DeepSeek API**：`https://api.deepseek.com/chat/completions`
- **默认模型**：`deepseek-chat`（备选 `deepseek-reasoner`，更慢但推理更深）
- **API Key 获取**：用户需提供，或已设置 `DEEPSEEK_API_KEY` 环境变量
</config>

<process>

## STEP 0 — 判断任务类型

| 场景 | 使用脚本 |
|------|----------|
| 分析单本书籍 | `scripts/book_analyzer.py` |
| 批量分析目录下所有书籍 | `scripts/book_analyzer_batch.py` |

---

## STEP 1 — 确认必要信息

运行前确认以下信息已知：

1. **书籍文件路径**（必须）：`.txt` 或 `.md` 格式
2. **DeepSeek API Key**（必须）：用户提供，或 `$DEEPSEEK_API_KEY` 环境变量
3. **输出路径**（可选）：默认在书籍同目录下生成 `<书名>_analysis.md`
4. **书名**（可选）：默认从文件名自动推断

如果用户未提供 API Key，提示：
> 请提供 DeepSeek API Key（可在 https://platform.deepseek.com 获取），或设置环境变量：
> `export DEEPSEEK_API_KEY=sk-xxx`

---

## STEP 2 — 单本书籍分析

```bash
python3 ~/.workbuddy/skills/book-analyzer/scripts/book_analyzer.py \
  "<书籍文件路径>" \
  --api-key "<DEEPSEEK_API_KEY>" \
  --output "<输出路径（可选）>" \
  --title "<书名（可选，默认从文件名推断）>" \
  --model deepseek-chat \
  --chunk 60000
```

**参数说明：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--api-key` | DeepSeek API Key | 读取 `$DEEPSEEK_API_KEY` |
| `--output` | 输出 Markdown 文件路径 | 同目录下 `<书名>_analysis.md` |
| `--title` | 手动指定书名 | 从文件名自动推断 |
| `--model` | 使用的模型 | `deepseek-chat` |
| `--chunk` | 分块字符数（超出自动分块摘要） | `60000` |
| `--encoding` | 文件编码 | `utf-8` |
| `--no-supplement` | 禁止自动补足100句金句 | 否 |
| `--preprocess` | 分析前自动修复 OCR 问题（默认开启） | 开启 |
| `--no-preprocess` | 跳过 OCR 预处理步骤 | 否 |

**OCR 书籍处理（同步修复标题层级）：**

对于 OCR 扫描或 PDF 转换的书籍，采用**按章节分块分析 + 同步修复标题**策略：

1. **智能分块**：按 H1 标题分割章节，确保每个块都是完整章节
2. **上下文感知**：每块分析时传入前后章节结构，LLM 可准确判断层级
3. **同步修复**：在章节分析过程中同步修复标题层级，不压缩原文
4. **层级判断**：根据章节编号和内容语义自动映射到 H1-H6

**分块策略：**
- 章节 ≤ 3 个：直接全文分析（不触发分块）
- 章节 > 3 个：按章节分块深度分析
- 每块最大 8000 字符，避免超出 token 限制

**超长书籍处理：**
- 书籍 ≤ 60000字：直接全文提交 DeepSeek 分析
- 书籍 > 60000字：自动分块 → 逐块摘要 → 合并摘要 → 最终深度分析
- 金句 < 95条：自动追加一轮请求补足至100条

如需跳过预处理：`--no-preprocess`

---

## STEP 3 — 批量分析目录

```bash
python3 ~/.workbuddy/skills/book-analyzer/scripts/book_analyzer_batch.py \
  "<书籍目录>" \
  --api-key "<DEEPSEEK_API_KEY>" \
  --output-dir "<输出目录（可选）>" \
  --ext "txt,md" \
  --skip-exists \
  --interval 3
```

**批量参数说明：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--output-dir` | 输出目录 | `<书籍目录>/analysis_output/` |
| `--ext` | 文件扩展名（逗号分隔） | `txt,md` |
| `--skip-exists` | 跳过已有分析结果的书籍 | 否 |
| `--interval` | 每本书之间等待秒数（避免限流） | `3` |
| `--glob` | 文件 glob 模式（优先级高于 `--ext`） | 无 |

---

## STEP 4 — 输出格式

每本书生成一个 `<书名>_analysis.md`，结构如下：

```markdown
# 《书名》深度分析报告

## 一、书籍概要
（200-300字，包含：成书背景、作者立场、核心议题、主要结构、写作风格）

## 二、核心主张与要求
**主张1**：...
**主张2**：...
...（共10条）

## 三、学术派系与思想谱系
（300字，说明学术流派归属、与经典理论的继承/对话/批判关系、在学术史上的位置）

## 四、100句金句
1. "金句原文" — 来源注释
2. ...
...（共100条）
```

---

## STEP 5 — 常见问题处理

| 问题 | 处理方式 |
|------|----------|
| API Key 无效 | 提示用户检查 key，或前往 https://platform.deepseek.com 获取 |
| 文件编码错误 | 尝试 `--encoding gbk` 或 `--encoding gb2312` |
| 金句不足 | 脚本自动补充，也可手动重跑 `--no-supplement` 后对比 |
| 书籍超大（>200万字） | 减小 `--chunk 40000` 分更多块；或先用 PDF 工具提取核心章节 |
| 限流 429 | 脚本自动重试3次；批量时增大 `--interval 10` |

</process>

<validation>
完成后确认：
- 输出 `.md` 文件已生成并不为空
- 包含四个章节（概要、核心主张、学术派系、100句金句）
- 金句数量 ≥ 95 条
- 告知用户输出文件的完整路径
</validation>
