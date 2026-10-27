---
name: guosai-docx-format
description: "Convert a Pandoc-generated Chinese research-paper .docx into 全国大学生统计建模大赛 (China National Undergraduate Statistical Modeling Contest) submission format. Trigger this whenever the user uploads a .docx that looks like a Chinese academic/thesis-style paper (特别是从 Markdown 用 pandoc 转出的那种) and asks to fix formatting, match 国赛 / 统计建模大赛 requirements, 严格按国赛标准 / 修格式 / 排版, or mentions 封面、摘要、目录、参考文献、附录 排版. Only use when the user explicitly names 统计建模大赛/国赛 or confirms this target format — do NOT default-trigger on any academic-looking docx. SKIP entirely for 华数杯 and other competitions (华数杯 format is different: 首页信息表+参赛编号、无目录、AI工具使用声明; applying 国赛 format there would be wrong). This skill rebuilds: cover page (赛事抬头 + 主标题 + 副标题), abstract block, auto-numbered headings (1 / 1.1 / 1.1.1), figure/table captions (图 N / 表 N), bibliography with [N] numbering and hanging indent, appendix with code blocks, centered page numbers, and strict page-break protection so figures and tables never get split across pages."
license: MIT
---

# 国赛统计建模 DOCX 格式化

## 这个 skill 是干什么的

把一份「用 pandoc 从 Markdown 转出来的中文学术论文 docx」改造成「全国大学生统计建模大赛」的提交格式。原始文档通常有这几个毛病，这个 skill 按顺序全部修复：

- 一级标题是「一、二、三、」中文编号（国赛要求阿拉伯数字 `1 2 3`）
- 没有封面区，或封面排列混乱（赛事信息被当成正文段）
- 摘要和关键词段没有独立样式
- 没有目录页
- 图题表题没有「图 N / 表 N」编号
- 表格行默认允许跨页切割
- 参考文献没有 `[N]` 序号也没有悬挂缩进
- 没有页码
- 公式里的 `CO₂` `R²` 这类下标上标被 pandoc 搞成空 `<m:e>` + 孤立 sub，渲染错位
- 「参考文献」「附录」没有另起一页

## 什么时候用它

Claude 应当主动触发这个 skill，不要等用户解释细节。触发信号：

- 用户上传 `.docx` 并提到「国赛」「统计建模大赛」「全国大学生」「建模比赛」
- 用户说「按国赛格式」「严格按要求」「修格式」「排版有问题」
- 用户上传一份明显是中文学术论文结构（有摘要、关键词、多级标题、参考文献、附录）的 docx，即便没说格式要求，也大概率是要改成国赛格式 —— 这是默认假设
- 用户说「这个也修一下」「再来一份」—— 说明是批处理同类文档

## 什么时候不用它

- 英文论文 / 非中文论文
- 非统计建模类的 docx（比如简历、合同、信件、报告）
- 用户已经在 Word 里排好版、只想做局部修改的
- 不是 pandoc 转出来的 docx（比如 Word 原生编辑的、WPS 导出的）—— 这个 skill 假设源文件有 `Heading1/2/3` `BodyText` `ImageCaption` `TableCaption` `Bibliography` 这套 pandoc 默认样式；用在别的模板上会失效

## 快速开始

**一键改造（推荐）**：

```bash
python3 scripts/apply_guosai_format.py 用户文件.docx 输出_国赛格式.docx
```

主驱动脚本会自动串联全部步骤：解包 → 替换样式 → 注册页脚 → 改标题编号 → 修公式 → 加图表编号 → 表格防切 → 参考文献加序号 → 加分页 → 打包校验。

**校验通过**的标志：最后一行输出 `✅ 校验通过`。

## 依赖

这个 skill 依赖 Anthropic 的 **docx skill** 提供 `unpack.py` 和 `pack.py`。脚本会按顺序在以下位置查找：

1. `/mnt/skills/public/docx/scripts/office/`（Anthropic 环境默认）
2. `~/docx-skill/scripts/office/`（本地安装）
3. `/opt/skills/docx/scripts/office/`

如果都没有，脚本会报错并列出需要放置的位置。docx skill 是 Anthropic proprietary 的，请确保可用。

除此之外只需要 Python 3.9+，无第三方库。

## 执行流程详解（Claude 阅读这段来理解该怎么用）

主驱动按 10 步执行。每一步都是独立的，出问题容易定位：

1. **解包** `input.docx` → 临时目录的 `unpacked/`
2. **替换 styles.xml**（用 `assets/styles.xml`）—— 定义 Title、Heading1-4、Abstract、AbstractTitle、BodyText、Bibliography、Caption、ImageCaption、TableCaption、SourceCode、Figure、CaptionedFigure 全套样式
3. **替换 numbering.xml**（用空文件）—— 干掉 pandoc 塞进去的"一、二、三"中文自动编号
4. **复制 footer1.xml** 到 word/，注册到 rels 和 [Content_Types].xml；同时加 png/jpeg Default 扩展声明
5. **step1_fix_headings.py**：把"参考文献""附录"升格为 Heading1；参考文献区间内条目改 Bibliography 样式；给 Heading1/2/3 加阿拉伯数字编号
6. **step2_fix_math.py**：把 pandoc 产生的空 `<m:e>` + sub/sup 的 oMath 替换成标准 Word vertAlign 下标/上标 run；清理零宽字符
7. **step3_caption_prefix.py**：给 ImageCaption 加"图 N"前缀，TableCaption 加"表 N"前缀
8. **step4_cantsplit.py**：给所有 `<w:tr>` 加 `<w:cantSplit/>` 防跨页切割
9. **step5_pagebreak.py**：在"参考文献""附录"Heading1 段的 pPr 里加 `<w:pageBreakBefore/>`
10. **step6_ref_number.py**：给每个 Bibliography 段开头加 `[N]` 序号
11. **add_footer_reference**：在 sectPr 里插入 `<w:footerReference>`（必须紧跟 sectPr 开标签，在 footnotePr 之前）
12. **pack.py**：打包 + 校验

## 输出是什么样子的

- **A4 纸、上下 2.54 cm、左右 3.17 cm**（原样保留）
- **封面**：赛事抬头（四号黑体加粗居中）→ 主标题（小二黑体 18pt 居中）→ 副标题（四号楷体居中）
- **摘要**：「摘要」小三黑体居中 → 正文 Abstract 样式（小四宋体首行缩进 1.3 倍行距）
- **关键词**：「**关键词：**」黑体加粗 + 宋体
- **目录页**：独立一页，含 TOC 域（Word 里按 F9 自动填充）
- **正文**：小四宋体 12pt，首行缩进 2 字符，1.5 倍行距
- **标题**：H1 三号黑体 16pt 居中，H2 四号黑体 14pt 左对齐，H3 小四黑体 12pt 左对齐，H4 小四楷体 12pt
- **图题**：黑体加粗居中，置于图下，"图 N" 自动编号
- **表题**：黑体加粗居中，置于表上，"表 N" 自动编号
- **参考文献**：另起一页，五号宋体 10.5pt，`[N]` 序号 + 悬挂缩进 2 字符
- **附录**：另起一页；代码段用 SourceCode 样式（Consolas 等宽 10pt + 保留 pandoc 语法高亮）
- **页码**：五号宋体居中

## 关键实现细节

### 为什么 `pageBreakBefore` 位置不能乱

OOXML schema 对 `<w:pPr>` 子元素的顺序有严格要求：

```
pStyle → keepNext/keepLines → pageBreakBefore → framePr → widowControl → ... → numPr → ... → spacing → ind → jc → ... → rPr
```

放错了位置会让 `pack.py` 的 schema 校验直接报 `This element is not expected`。step5_pagebreak.py 把 `<w:pageBreakBefore/>` 插在 `</w:pPr>` 前紧跟 `<w:pStyle>` 之后，是唯一安全位置。

### 为什么 `footerReference` 在 `footnotePr` 之前

sectPr 的子元素顺序也是由 schema 规定的：`footerReference`/`headerReference` 必须在 `footnotePr` 之前。反了就会校验失败。这个点在 `add_footer_reference` 里已经处理。

### 封面主标题如果过长怎么办

默认样式给主标题设的是小二号 18pt 黑体。如果标题超过约 20 个汉字会自动换行，Word 的自动换行点可能落在语义不好的位置（比如把"预警"拆成"预 / 警"）。遇到这种情况，可以手动在 document.xml 的主标题段里插入 `<w:br/>` 强制换行点。例子：

```xml
<w:t>极端气候事件对区域粮食产量的</w:t>
<w:br/>
<w:t>非线性冲击与安全预警模型</w:t>
```

这一步脚本没有自动化（因为不知道用户想在哪里断），但如果 Claude 发现主标题长、预渲染效果不理想，可以主动问用户是否要加手动换行。

### 摘要太长会溢出首页

默认 Abstract 样式的行距是 1.3 倍（line=320）、段前 60 twip、段后 120 twip。这是为了让典型 600–800 字的摘要+关键词能完整落在首页一张内。如果摘要还是过长：

- 再把 `line` 调到 `280`（1.2 倍行距）
- 或者降低主标题前的 `before` 留白

样式改在 `assets/styles.xml` 的 `Abstract` 定义里。

### 附录代码段为什么不加灰底

原始 pandoc 生成的 docx 里，代码段已经是 SourceCode 样式，run 里带着 `KeywordTok` / `DecValTok` 等语法高亮 character style（关键字绿、数字绿、字符串黄）。纯白背景 + 语法高亮比灰底 + 黑字更清爽，就没加背景色。要加的话改 `assets/styles.xml` 里的 SourceCode 定义，加 `<w:shd w:fill="F5F5F5" w:val="clear"/>` 即可。

## 已验证的三份真实案例

开发过程中在三份真实国赛投稿 docx 上逐个调试、最终无需人工修改就能一键输出通过校验的文档：

1. 碳排放双控目标进度监测方法（39 页，12 图 9 表）
2. 生成式 AI 对知识型劳动力市场的结构性冲击（42 页，14 图 4 表）
3. 极端气候事件对区域粮食产量的非线性冲击（现标题手动换行后 43 页，7 图 11 表）

三份都成功：标题编号正确、图表完整不切、封面一页式收入摘要关键词、参考文献悬挂缩进 + [N] 序号、附录代码带语法高亮。

## 脚本文件清单

```
guosai-docx-format/
├── SKILL.md                         # 本文件
├── assets/
│   ├── styles.xml                   # 调好的 Word 样式库
│   ├── numbering.xml                # 空 numbering（用来干掉中文自动编号）
│   └── footer1.xml                  # 页码居中的页脚定义
└── scripts/
    ├── apply_guosai_format.py       # 主驱动
    ├── step1_fix_headings.py        # 标题样式 + 编号
    ├── step2_fix_math.py            # 公式下标/上标
    ├── step3_caption_prefix.py      # 图题/表题编号
    ├── step4_cantsplit.py           # 表格行防切
    ├── step5_pagebreak.py           # 参考文献/附录另起页
    └── step6_ref_number.py          # 参考文献 [N] 序号
```

## 返回给用户的东西

生成 `.docx` 文件后，**务必提醒用户在 Word 里打开，按 F9 或右键目录区 → 更新域**，这样目录才会从"占位符"变成真正的条目列表。LibreOffice 不会自动执行这个域，所以预览 PDF 的目录页会是空的，这属于正常现象。
