#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step7_insert_toc.py —— 在首个 Heading1 标题前插入目录页

Word 的 TOC 域在加载时是占位符状态，用户需要按 F9 手动更新一次才会
生成真正的目录条目。这一步只负责插入占位符结构。

做两件事：
1. 在第一个 Heading1 段之前插入：
   - "目  录" 标题段（黑体小三居中、pageBreakBefore）
   - TOC 域段（dot leader 到 9062 twip 右对齐）
2. 给第一个 Heading1 段也加 pageBreakBefore（让引言从新页开始）
"""
import re
import sys
from pathlib import Path


def insert_toc(unpacked: Path):
    doc_path = unpacked / "word" / "document.xml"
    content = doc_path.read_text(encoding="utf-8")

    # 找第一个 Heading1 段（编号后的"1  XX"格式）
    first_h1_pattern = re.compile(
        r'(<w:bookmarkStart[^/]*?/>\s*)?(<w:p>\s*<w:pPr>\s*<w:pStyle w:val="Heading1"/>\s*</w:pPr>\s*'
        r'<w:r>\s*<w:rPr>\s*<w:rFonts w:hint="eastAsia"/>\s*</w:rPr>\s*'
        r'<w:t xml:space="preserve">1  [^<]+</w:t>\s*</w:r>\s*</w:p>)'
    )
    m = first_h1_pattern.search(content)
    if not m:
        print("  找不到第一个带编号的 Heading1（如 '1 引言'），跳过目录")
        return

    bookmark = m.group(1) or ""
    h1_block = m.group(2)

    # 给 h1_block 的 pPr 加 pageBreakBefore
    h1_with_break = h1_block.replace(
        '<w:pStyle w:val="Heading1"/>',
        '<w:pStyle w:val="Heading1"/>\n        <w:pageBreakBefore/>',
        1
    )

    toc_xml = '''
    <w:p>
      <w:pPr>
        <w:pStyle w:val="Normal"/>
        <w:pageBreakBefore/>
        <w:spacing w:before="240" w:after="240" w:line="360" w:lineRule="auto"/>
        <w:ind w:firstLine="0" w:firstLineChars="0"/>
        <w:jc w:val="center"/>
      </w:pPr>
      <w:r>
        <w:rPr>
          <w:rFonts w:ascii="SimHei" w:hAnsi="SimHei" w:eastAsia="SimHei" w:cs="SimHei" w:hint="eastAsia"/>
          <w:b/>
          <w:bCs/>
          <w:sz w:val="32"/>
          <w:szCs w:val="32"/>
        </w:rPr>
        <w:t xml:space="preserve">目  录</w:t>
      </w:r>
    </w:p>
    <w:p>
      <w:pPr>
        <w:pStyle w:val="Normal"/>
        <w:tabs>
          <w:tab w:val="right" w:leader="dot" w:pos="9062"/>
        </w:tabs>
        <w:spacing w:before="0" w:after="0" w:line="360" w:lineRule="auto"/>
        <w:ind w:firstLine="0" w:firstLineChars="0"/>
      </w:pPr>
      <w:r>
        <w:fldChar w:fldCharType="begin" w:dirty="true"/>
      </w:r>
      <w:r>
        <w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText>
      </w:r>
      <w:r>
        <w:fldChar w:fldCharType="separate"/>
      </w:r>
      <w:r>
        <w:rPr>
          <w:rFonts w:hint="eastAsia"/>
        </w:rPr>
        <w:t xml:space="preserve">右键点击此处 → 更新域，可生成完整目录</w:t>
      </w:r>
      <w:r>
        <w:fldChar w:fldCharType="end"/>
      </w:r>
    </w:p>
'''

    replacement = toc_xml + "    " + bookmark + h1_with_break
    content = content[:m.start()] + replacement + content[m.end():]

    doc_path.write_text(content, encoding="utf-8")
    print("  目录页已插入（Word 打开按 F9 即可生成条目）")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python3 step7_insert_toc.py <unpacked_dir>")
        sys.exit(1)
    insert_toc(Path(sys.argv[1]))
