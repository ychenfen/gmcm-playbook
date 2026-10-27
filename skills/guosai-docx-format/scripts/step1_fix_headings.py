#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step1_fix_headings.py —— 修复标题结构

1. 把"参考文献""附录"（原先可能用 BodyText）升级为 Heading1
2. 把"参考文献"区间内的条目段全部改为 Bibliography 样式
3. 给所有 Heading1/2/3 按层级加阿拉伯数字编号（1, 1.1, 1.1.1）
   "参考文献" / "附录" 两个特殊章节不加编号
   "附录" 下的子节（附录A/B/C）保留原名不加 N.N 编号

用法: python3 step1_fix_headings.py <unpacked_dir>
"""
import re
import sys
from pathlib import Path


def fix_headings(unpacked_dir: Path):
    doc_path = unpacked_dir / "word" / "document.xml"
    content = doc_path.read_text(encoding="utf-8")

    # --- 1. "参考文献"和"附录"标题升格为 Heading1 ---
    def upgrade_heading(title: str, xml: str) -> tuple[str, int]:
        pattern = re.compile(
            r'<w:p>\s*<w:pPr>\s*<w:pStyle w:val="BodyText"/>\s*</w:pPr>\s*'
            r'<w:r>\s*<w:rPr>\s*<w:rFonts w:hint="eastAsia"/>\s*</w:rPr>\s*'
            r'<w:t xml:space="preserve">' + re.escape(title) + r'</w:t>\s*</w:r>\s*</w:p>'
        )
        replacement = (
            '<w:p>\n      <w:pPr>\n        <w:pStyle w:val="Heading1"/>\n      </w:pPr>\n'
            '      <w:r>\n        <w:rPr>\n          <w:rFonts w:hint="eastAsia"/>\n        </w:rPr>\n'
            f'        <w:t xml:space="preserve">{title}</w:t>\n      </w:r>\n    </w:p>'
        )
        n = len(pattern.findall(xml))
        return pattern.sub(replacement, xml), n

    content, n1 = upgrade_heading("参考文献", content)
    print(f"  参考文献标题升级: {n1} 处")
    content, n2 = upgrade_heading("附录", content)
    print(f"  附录标题升级: {n2} 处")

    # --- 2. 参考文献区间内的条目改为 Bibliography 样式 ---
    refhead_match = re.search(
        r'<w:p>\s*<w:pPr>\s*<w:pStyle w:val="Heading1"/>\s*</w:pPr>\s*'
        r'<w:r>[^<]*<w:rPr>[^<]*<w:rFonts w:hint="eastAsia"/>[^<]*</w:rPr>\s*'
        r'<w:t xml:space="preserve">参考文献</w:t>',
        content
    )
    apphead_match = re.search(
        r'<w:p>\s*<w:pPr>\s*<w:pStyle w:val="Heading1"/>\s*</w:pPr>\s*'
        r'<w:r>[^<]*<w:rPr>[^<]*<w:rFonts w:hint="eastAsia"/>[^<]*</w:rPr>\s*'
        r'<w:t xml:space="preserve">附录</w:t>',
        content
    )
    if refhead_match and apphead_match:
        ref_start = refhead_match.end()
        ref_end = apphead_match.start()
        ref_section = content[ref_start:ref_end]
        n3 = ref_section.count('<w:pStyle w:val="BodyText"/>')
        ref_section_new = ref_section.replace(
            '<w:pStyle w:val="BodyText"/>',
            '<w:pStyle w:val="Bibliography"/>'
        )
        content = content[:ref_start] + ref_section_new + content[ref_end:]
        print(f"  参考文献条目改 Bibliography: {n3} 处")

    # --- 3. 给标题加阿拉伯数字编号 ---
    # 鲁棒匹配：整段 Heading 段落（不要求首个 run 是中文，兼容 "OLS 回归"
    # "Lasso 与岭回归" 这类以拉丁字母开头、被 pandoc 拆成多 run 的标题），
    # 把编号前缀插到段内第一个 <w:t> 内容前。
    heading_para_pattern = re.compile(
        r'<w:p>\s*<w:pPr>\s*<w:pStyle w:val="Heading([1-3])"/>.*?</w:p>',
        re.DOTALL
    )
    # 不编号的特殊一级标题（致谢/参考文献/附录，含全角或 \quad 空格变体）
    SPECIAL_H1 = {"参考文献", "附录", "致谢", "致辞", "前言", "声明"}

    state = {"h1": 0, "h2": 0, "h3": 0, "in_appendix": False}

    def number_heading(m):
        block = m.group(0)
        level = int(m.group(1))
        full_text = ''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', block))
        clean = full_text.replace(" ", "").replace("　", "").strip()

        if level == 1:
            if clean == "附录":
                state["in_appendix"] = True
                return block
            if clean in SPECIAL_H1:
                state["in_appendix"] = False
                return block
            state["in_appendix"] = False
            state["h1"] += 1
            state["h2"] = 0
            state["h3"] = 0
            num = f"{state['h1']}  "
        elif level == 2:
            if state["in_appendix"]:
                return block            # 附录 A/B/C 保留原名不加 N.N 编号
            state["h2"] += 1
            state["h3"] = 0
            num = f"{state['h1']}.{state['h2']}  "
        else:
            state["h3"] += 1
            num = f"{state['h1']}.{state['h2']}.{state['h3']}  "

        # 把编号插到段内第一个 <w:t ...> 内容之前（保留原 run 结构）
        # 用函数式替换，避免 num 以数字开头时与 \1 拼成歧义反向引用
        return re.sub(r'(<w:t[^>]*>)', lambda mm: mm.group(1) + num, block, count=1)

    content = heading_para_pattern.sub(number_heading, content)
    print(f"  正文一级标题编号到: {state['h1']}")

    doc_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python3 step1_fix_headings.py <unpacked_dir>")
        sys.exit(1)
    fix_headings(Path(sys.argv[1]))
