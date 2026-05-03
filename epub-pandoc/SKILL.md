---
name: epub-pandoc
description: "Pandoc-driven EPUB → Markdown 转换。适用于将 EPUB（如 The Economist 样刊）转换为结构化 Markdown 文件（章节+图片），输出格式与 epub-read skill 的 parse_epub.py 兼容。当用户提及 EPUB 解析、经济学人转 Markdown、Pandoc 转换时触发。"
agent_created: true
---

# epub-pandoc — Pandoc 驱动的 EPUB→Markdown 转换

## 何时使用

用户提到以下内容时触发：
- 解析/转换 EPUB 到 Markdown
- The Economist / 经济学人 EPUB 处理
- Pandoc 转换 EPUB
- 提取 EPUB 内图片/章节

## 工作流

### 1. 转换脚本位置

- **脚本**：`{workspace}/infohub/scripts/epub_pandoc.py`（在 infohub 项目内）
- **依赖**：系统安装 `pandoc`、Python 3.9+、`beautifulsoup4` + `lxml`

### 2. 基本用法

```bash
cd {workspace}/infohub
python3 scripts/epub_pandoc.py /path/to/file.epub --output-dir OUTPUT_DIR --book-id BOOK_ID
```

输出目录结构：
```
OUTPUT_DIR/BOOK_ID/
├── metadata.json   # 书籍元数据
├── toc.json        # 目录
├── book.json       # 章节列表（含全文）
├── manifest.json   # 输出清单
├── chapters/       # 每章独立 Markdown 文件
└── images/         # 提取的图片
```

### 3. 输出格式

- 每章文件：`ch{编号:03d}-{slug}.md`
- 标题格式：`# {标题}` 作为正文开头
- 图片引用：`![](images/{文件名})`
- 双语翻译已在采集层处理，脚本不处理翻译

### 4. 已知 Bug 与修复记录

| 问题 | 表现 | 修复位置 |
|------|------|----------|
| `# ## Obituary` 双标题 | Pandoc 输出 `# ## Obituary`，clean_markdown 修复后 title 提取依然拿到 `## Obituary`，组装 `# {title}` 再次引入 | line 461-462: 从正文移除第一个 `#` 标题行 |
| Masthead slug 混乱 | 封面图片 `!masthead(image.jpg)` 被当作标题 | line 458-459: 纯图片标题替换为 "Masthead" |
| XMLParsedAsHTMLWarning | bs4 解析 XHTML 每页一条警告 | line 38: 显式 `category=XMLParsedAsHTMLWarning` 过滤 |
| `:::div` 残留 | 前导空格导致未匹配 | clean_markdown step 2: `^` → `^[ \t]*` |
| `!Title(image.jpg)` 未转 Markdown | 图片作为 ![](image.jpg) 未正确渲染 | clean_markdown step 9b |
| `../../feed_#` 内部链接 | EPUB 内部引用未被清除 | clean_markdown step 7 模式 B |

### 5. 验证方法

转换后验证以下 7 项：
1. `# ##` 双标题零残留 → `grep -rn '^# ##' chapters/`
2. `:::` div 零残留 → `grep -rn '^::' chapters/`
3. 内部链接零残留 → `grep -rn 'feed_\|\.\.\/' chapters/`（排除 images/）
4. `!Title()` 模式零残留 → `grep -rn '^![[alnum:]]' chapters/`
5. 图片引用全部为 `![](images/...)` 格式
6. XMLParsedAsHTMLWarning 零出现（stderr 空）
7. 章节数 + 图片数与 manifest.json 一致

### 6. 与 epub-read skill 的关系

`epub_pandoc.py` 是 `parse_epub.py`（epub-read skill 内）的替代方案。输出目录结构兼容。
- pandoc 方案优势：更好的 drop cap / R&D / 句子重复处理
- pandoc 方案劣势：需要系统安装 pandoc
