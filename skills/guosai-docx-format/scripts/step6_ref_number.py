#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step6_ref_number.py —— 给参考文献每条加 [N] 序号

扫描所有 pStyle=Bibliography 的段落，从 1 开始依次加 [1]、[2]、...
"""
import re
import sys
from pathlib import Path


def add_ref_number(unpacked_dir: Path):
    doc_path = unpacked_dir / "word" / "document.xml"
    content = doc_path.read_text(encoding="utf-8")

    counter = [0]
    pattern = re.compile(
        r'(<w:p>\s*<w:pPr>\s*<w:pStyle w:val="Bibliography"/>\s*</w:pPr>)(\s*)',
        re.DOTALL
    )

    def add_number(m):
        counter[0] += 1
        prefix_run = (
            '\n      <w:r>'
            f'<w:t xml:space="preserve">[{counter[0]}] </w:t>'
            '</w:r>'
        )
        return m.group(1) + prefix_run + m.group(2)

    content = pattern.sub(add_number, content)
    print(f"  已为 {counter[0]} 条参考文献添加序号")

    doc_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python3 step6_ref_number.py <unpacked_dir>")
        sys.exit(1)
    add_ref_number(Path(sys.argv[1]))
