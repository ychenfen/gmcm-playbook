#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step3_caption_prefix.py —— 给图题、表题加"图 N" / "表 N"编号前缀

国赛要求图题、表题统一加阿拉伯数字编号。扫描全文：
- 所有 pStyle=ImageCaption 的段从 1 开始编号，前加"图 N "
- 所有 pStyle=TableCaption 的段从 1 开始编号，前加"表 N "
"""
import re
import sys
from pathlib import Path


def add_prefix(unpacked_dir: Path):
    doc_path = unpacked_dir / "word" / "document.xml"
    content = doc_path.read_text(encoding="utf-8")

    def process(style: str, prefix_word: str, xml: str) -> tuple[str, int]:
        counter = [0]
        p_re = re.compile(
            r'(<w:p>\s*<w:pPr>\s*<w:pStyle w:val="' + style + r'"/>\s*</w:pPr>)'
            r'(.*?)(</w:p>)',
            re.DOTALL
        )

        def repl(m):
            counter[0] += 1
            prefix_run = (
                '\n      <w:r>'
                '<w:rPr><w:rFonts w:hint="eastAsia"/></w:rPr>'
                f'<w:t xml:space="preserve">{prefix_word} {counter[0]}  </w:t>'
                '</w:r>'
            )
            return m.group(1) + prefix_run + m.group(2) + m.group(3)

        xml = p_re.sub(repl, xml)
        return xml, counter[0]

    content, n_img = process("ImageCaption", "图", content)
    print(f"  图题编号: {n_img} 处")
    content, n_tbl = process("TableCaption", "表", content)
    print(f"  表题编号: {n_tbl} 处")

    doc_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python3 step3_caption_prefix.py <unpacked_dir>")
        sys.exit(1)
    add_prefix(Path(sys.argv[1]))
