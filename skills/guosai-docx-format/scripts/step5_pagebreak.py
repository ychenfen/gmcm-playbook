#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step5_pagebreak.py —— 在"参考文献"和"附录"一级标题前加分页符

国赛惯例：参考文献、附录各自起始于新的一页。
实现方式：在对应的 Heading1 段的 <w:pPr> 里加 <w:pageBreakBefore/>。

注意 OOXML schema 对 pPr 子元素顺序有严格要求：
pStyle → keepNext/keepLines → pageBreakBefore → framePr → widowControl → ...
所以 pageBreakBefore 必须紧跟 pStyle。
"""
import re
import sys
from pathlib import Path


def add_pagebreak(unpacked_dir: Path):
    doc_path = unpacked_dir / "word" / "document.xml"
    content = doc_path.read_text(encoding="utf-8")

    pattern = re.compile(
        r'(<w:p>\s*<w:pPr>\s*<w:pStyle w:val="Heading1"/>)\s*(</w:pPr>\s*'
        r'<w:r>\s*<w:rPr>\s*<w:rFonts w:hint="eastAsia"/>\s*</w:rPr>\s*'
        r'<w:t xml:space="preserve">(?:参考文献|附录)</w:t>)'
    )

    n = len(pattern.findall(content))
    content = pattern.sub(
        lambda m: m.group(1) + '\n        <w:pageBreakBefore/>\n      ' + m.group(2),
        content
    )
    print(f"  添加分页符: {n} 处")

    doc_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python3 step5_pagebreak.py <unpacked_dir>")
        sys.exit(1)
    add_pagebreak(Path(sys.argv[1]))
