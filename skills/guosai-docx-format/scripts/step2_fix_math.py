#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step2_fix_math.py —— 修复 pandoc 转换产生的 oMath 下标/上标

pandoc 从 markdown 的 CO~2~ / R^2^ 转出的 oMath 结构有问题：
  <m:sSub><m:e><m:r><m:t>​</m:t></m:r></m:e><m:sub>...</m:sub></m:sSub>
空的 <m:e> + 孤立的 sub 会让 Word 里显示成一个飘在主文字后面的小字。
改写成标准 Word 下标 run：
  <w:r><w:rPr><w:vertAlign w:val="subscript"/></w:rPr><w:t>2</w:t></w:r>

同时清理残留的零宽字符 \u200b。
"""
import re
import sys
from pathlib import Path


def fix_math(unpacked_dir: Path):
    doc_path = unpacked_dir / "word" / "document.xml"
    content = doc_path.read_text(encoding="utf-8")

    # 下标：空 e + sub
    sub_pattern = re.compile(
        r'<m:oMath>\s*<m:sSub>\s*<m:e>\s*<m:r>\s*<m:t>[^<]*</m:t>\s*</m:r>\s*</m:e>\s*'
        r'<m:sub>\s*<m:r>\s*<m:t>([^<]+)</m:t>\s*</m:r>\s*</m:sub>\s*</m:sSub>\s*</m:oMath>',
        re.DOTALL
    )
    n_sub = len(sub_pattern.findall(content))
    content = sub_pattern.sub(
        lambda m: f'<w:r><w:rPr><w:vertAlign w:val="subscript"/></w:rPr><w:t xml:space="preserve">{m.group(1)}</w:t></w:r>',
        content
    )
    print(f"  下标修复: {n_sub} 处")

    # 上标：空 e + sup
    sup_pattern = re.compile(
        r'<m:oMath>\s*<m:sSup>\s*<m:e>\s*<m:r>\s*<m:t>[^<]*</m:t>\s*</m:r>\s*</m:e>\s*'
        r'<m:sup>\s*<m:r>\s*<m:t>([^<]+)</m:t>\s*</m:r>\s*</m:sup>\s*</m:sSup>\s*</m:oMath>',
        re.DOTALL
    )
    n_sup = len(sup_pattern.findall(content))
    content = sup_pattern.sub(
        lambda m: f'<w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:t xml:space="preserve">{m.group(1)}</w:t></w:r>',
        content
    )
    print(f"  上标修复: {n_sup} 处")

    # 清除零宽字符
    n_zw = content.count("\u200b")
    content = content.replace("\u200b", "")
    print(f"  零宽字符清除: {n_zw} 处")

    doc_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python3 step2_fix_math.py <unpacked_dir>")
        sys.exit(1)
    fix_math(Path(sys.argv[1]))
