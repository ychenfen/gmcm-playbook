#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step4_cantsplit.py —— 给所有表格行加 <w:cantSplit/> 防跨页切割

Word 表格的默认行为是允许单行在页面底部被撕开上下页显示。
统计建模论文的数据表一般行高都不高，整行切开会非常难看。
本脚本给每个 <w:tr> 注入 <w:cantSplit/>：
- 已有 <w:trPr> 的行：在 trPr 块内追加 <w:cantSplit/>（若未存在）
- 没有 <w:trPr> 的行：新建 <w:trPr><w:cantSplit/></w:trPr>
"""
import re
import sys
from pathlib import Path


def add_cantsplit(unpacked_dir: Path):
    doc_path = unpacked_dir / "word" / "document.xml"
    content = doc_path.read_text(encoding="utf-8")

    # Case A: 已有 <w:trPr>...</w:trPr>
    existing_pattern = re.compile(r'<w:trPr>.*?</w:trPr>', re.DOTALL)
    n_existing = [0]

    def append_cantsplit(m):
        block = m.group(0)
        if 'cantSplit' in block:
            return block
        n_existing[0] += 1
        return block.replace('<w:trPr>', '<w:trPr>\n          <w:cantSplit/>', 1)

    content = existing_pattern.sub(append_cantsplit, content)
    print(f"  已有 trPr 加 cantSplit: {n_existing[0]} 处")

    # Case B: <w:tr> 后直接跟 <w:tc>（没 trPr）
    missing_pattern = re.compile(r'<w:tr>(\s*)<w:tc', re.DOTALL)
    n_missing = [0]

    def add_new_trpr(m):
        n_missing[0] += 1
        return (
            '<w:tr>\n        <w:trPr>\n          <w:cantSplit/>\n        </w:trPr>'
            + m.group(1) + '<w:tc'
        )

    content = missing_pattern.sub(add_new_trpr, content)
    print(f"  新建 trPr 带 cantSplit: {n_missing[0]} 处")

    doc_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python3 step4_cantsplit.py <unpacked_dir>")
        sys.exit(1)
    add_cantsplit(Path(sys.argv[1]))
