#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step0_rebuild_cover.py —— 重组封面区

pandoc 生成的 docx 封面区布局很乱：
- "2026年（第十二届）全国大学生统计建模大赛" 被拆成两行、用 FirstParagraph 样式
- 论文主标题往往用 pStyle="Title" 带多余的首尾空格
- 副标题（"—— 基于..."）独立成段用 BodyText
- "摘要" 标签是普通 BodyText 段

这个脚本把开头到"摘要"段之间的所有段落重新组装成国赛封面：
    赛事抬头（四号黑体加粗居中）
    主标题（小二黑体 18pt 居中）
    副标题（四号楷体居中）
    "摘要"（AbstractTitle 样式居中）
    摘要正文（Abstract 样式）

核心识别逻辑：
1. 正文首段到"摘要"段之间的所有段落，按文字内容分类：
   - 含"2026年"+"大赛" → 赛事抬头
   - 含"——"开头或全角"—— " → 副标题
   - "摘要" → 分界点
   - 其余 → 主标题候选（取最长或最先出现的非赛事、非副标题段）
2. 用新结构替换
"""
import re
import sys
from pathlib import Path


def rebuild_cover(unpacked: Path):
    doc_path = unpacked / "word" / "document.xml"
    content = doc_path.read_text(encoding="utf-8")

    # 找出 <w:body> 到"摘要"段末尾的片段
    body_start = content.find("<w:body>")
    if body_start < 0:
        print("  找不到 <w:body>，跳过封面重组")
        return
    body_content_start = body_start + len("<w:body>")

    # 找"摘要"段的结束位置（包括它自己）
    abstract_match = re.search(
        r'<w:p>\s*<w:pPr>\s*<w:pStyle w:val="[^"]+"/>\s*</w:pPr>\s*'
        r'<w:r>\s*<w:rPr>\s*<w:rFonts w:hint="eastAsia"/>\s*</w:rPr>\s*'
        r'<w:t xml:space="preserve">摘要</w:t>\s*</w:r>\s*</w:p>',
        content
    )
    if not abstract_match:
        print("  找不到'摘要'标题段，跳过封面重组")
        return
    cover_end = abstract_match.end()

    # 提取封面区里所有段落的纯文字（顺序）
    cover_xml = content[body_content_start:cover_end]
    texts = []
    for p_match in re.finditer(r'<w:p>.*?</w:p>', cover_xml, re.DOTALL):
        p_text = ''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', p_match.group(0)))
        # 合并段落内换行
        p_text = p_text.replace('\n', '').strip()
        if p_text:
            texts.append(p_text)

    if not texts:
        print("  封面区空，跳过")
        return

    # 分类
    contest_title = None   # 赛事抬头
    paper_title = None     # 主标题
    sub_title = None       # 副标题

    for t in texts:
        if t == "摘要":
            continue
        if "2026" in t and ("大赛" in t or "建模" in t):
            # 合并两段赛事抬头为一行
            contest_title = "2026年（第十二届）全国大学生统计建模大赛"
        elif t.strip().startswith("——") or t.strip().startswith("— —") or t.strip().startswith("- -"):
            # 副标题
            sub_title = t.strip()
            # 规范化成"—— xxx"
            sub_title = re.sub(r'^[—\-—\s]+', '—— ', sub_title)
        else:
            # 主标题候选：取最长的那一段（通常主标题比副标题长）
            if paper_title is None or len(t) > len(paper_title):
                # 跳过太短的碎片
                if len(t) >= 6:
                    if paper_title:
                        # 如果已经有候选，取更长的那个；被替换的如果含"——"可能是副标题
                        if not sub_title and paper_title.strip().startswith("——"):
                            sub_title = paper_title.strip()
                    paper_title = t

    if not paper_title:
        # 兜底：用第一个非"摘要"的段
        for t in texts:
            if t != "摘要" and "2026" not in t:
                paper_title = t
                break

    if not paper_title:
        print("  找不到主标题，跳过封面重组")
        return

    if not contest_title:
        contest_title = "2026年（第十二届）全国大学生统计建模大赛"

    # 清洗主标题里的多余空格
    paper_title = paper_title.strip()

    # 构造新封面 XML（按国赛官方模板字体）
    # 1. 作品编号（黑体三号）
    # 2. 赛事抬头（方正小标宋简体二号）
    # 3. 参赛作品（方正小标宋简体一号）
    # 4. 论文主标题（仿宋小二号）
    # 5. 副标题（仿宋四号）
    # 作品编号按用户要求不加（国赛参赛作品封面匿名，编号由组委会分配）
    new_cover_xml = f'''
    <w:p>
      <w:pPr>
        <w:pStyle w:val="Normal"/>
        <w:spacing w:before="1200" w:after="120" w:line="540" w:lineRule="exact"/>
        <w:ind w:firstLine="0" w:firstLineChars="0"/>
        <w:jc w:val="center"/>
      </w:pPr>
      <w:r>
        <w:rPr>
          <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="FZXiaoBiaoSong-B05S" w:cs="Times New Roman" w:hint="eastAsia"/>
          <w:sz w:val="32"/>
          <w:szCs w:val="32"/>
        </w:rPr>
        <w:t xml:space="preserve">{contest_title}</w:t>
      </w:r>
    </w:p>
    <w:p>
      <w:pPr>
        <w:pStyle w:val="Normal"/>
        <w:spacing w:before="240" w:after="600" w:line="540" w:lineRule="exact"/>
        <w:ind w:firstLine="0" w:firstLineChars="0"/>
        <w:jc w:val="center"/>
      </w:pPr>
      <w:r>
        <w:rPr>
          <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="FZXiaoBiaoSong-B05S" w:cs="Times New Roman" w:hint="eastAsia"/>
          <w:sz w:val="42"/>
          <w:szCs w:val="42"/>
        </w:rPr>
        <w:t xml:space="preserve">参 赛 作 品</w:t>
      </w:r>
    </w:p>
    <w:p>
      <w:pPr>
        <w:pStyle w:val="Normal"/>
        <w:spacing w:before="600" w:after="120" w:line="540" w:lineRule="exact"/>
        <w:ind w:firstLine="0" w:firstLineChars="0"/>
        <w:jc w:val="center"/>
      </w:pPr>
      <w:r>
        <w:rPr>
          <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="STFangsong" w:cs="Times New Roman" w:hint="eastAsia"/>
          <w:sz w:val="36"/>
          <w:szCs w:val="36"/>
        </w:rPr>
        <w:t xml:space="preserve">{paper_title}</w:t>
      </w:r>
    </w:p>'''

    if sub_title:
        new_cover_xml += f'''
    <w:p>
      <w:pPr>
        <w:pStyle w:val="Normal"/>
        <w:spacing w:before="0" w:after="360" w:line="480" w:lineRule="exact"/>
        <w:ind w:firstLine="0" w:firstLineChars="0"/>
        <w:jc w:val="center"/>
      </w:pPr>
      <w:r>
        <w:rPr>
          <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="STFangsong" w:cs="Times New Roman" w:hint="eastAsia"/>
          <w:sz w:val="28"/>
          <w:szCs w:val="28"/>
        </w:rPr>
        <w:t xml:space="preserve">{sub_title}</w:t>
      </w:r>
    </w:p>'''

    # 院校/队员/指导/组别按用户要求不加（国赛参赛作品封面匿名评审）；底部只留日期
    new_cover_xml += '''
    <w:p>
      <w:pPr>
        <w:pStyle w:val="Normal"/>
        <w:spacing w:before="3200" w:after="0" w:line="480" w:lineRule="exact"/>
        <w:ind w:firstLine="0" w:firstLineChars="0"/>
        <w:jc w:val="center"/>
      </w:pPr>
      <w:r>
        <w:rPr>
          <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="SimSun" w:cs="Times New Roman" w:hint="eastAsia"/>
          <w:sz w:val="28"/>
          <w:szCs w:val="28"/>
        </w:rPr>
        <w:t xml:space="preserve">2026 年 5 月</w:t>
      </w:r>
    </w:p>
    <w:p>
      <w:pPr>
        <w:pStyle w:val="Normal"/>
      </w:pPr>
      <w:r>
        <w:br w:type="page"/>
      </w:r>
    </w:p>'''

    new_cover_xml += '''
    <w:p>
      <w:pPr>
        <w:pStyle w:val="AbstractTitle"/>
      </w:pPr>
      <w:r>
        <w:rPr>
          <w:rFonts w:hint="eastAsia"/>
        </w:rPr>
        <w:t xml:space="preserve">摘要</w:t>
      </w:r>
    </w:p>
'''

    # 替换原封面区
    new_content = content[:body_content_start] + new_cover_xml + content[cover_end:]

    # 顺便把紧跟"摘要"之后的第一段 BodyText 改为 Abstract 样式
    # 找 <w:body> 后第一个摘要标题段的位置
    new_abstract_match = re.search(
        r'(<w:p>\s*<w:pPr>\s*<w:pStyle w:val="AbstractTitle"/>\s*</w:pPr>\s*'
        r'<w:r>[^<]*<w:rPr>[^<]*<w:rFonts w:hint="eastAsia"/>[^<]*</w:rPr>\s*'
        r'<w:t xml:space="preserve">摘要</w:t>\s*</w:r>\s*</w:p>\s*'
        r'<w:p>\s*<w:pPr>\s*)<w:pStyle w:val="BodyText"/>',
        new_content
    )
    if new_abstract_match:
        new_content = (
            new_content[:new_abstract_match.start(0)]
            + new_abstract_match.group(1).replace(
                '<w:p>\n      <w:pPr>\n        ',
                '<w:p>\n      <w:pPr>\n        '
            )
            + '<w:pStyle w:val="Abstract"/>'
            + new_content[new_abstract_match.end(0):]
        )

    # 找关键词段（紧跟摘要正文）把它也改成 Abstract 样式，加黑体前缀
    kw_match = re.search(
        r'<w:p>\s*<w:pPr>\s*<w:pStyle w:val="BodyText"/>\s*</w:pPr>\s*'
        r'<w:r>\s*<w:rPr>\s*<w:rFonts w:hint="eastAsia"/>\s*<w:b/>\s*<w:bCs/>\s*</w:rPr>\s*'
        r'<w:t xml:space="preserve">关键词：</w:t>',
        new_content
    )
    if kw_match:
        # 替换这段的 pPr 为 Abstract + 无首行缩进，rPr 里加黑体
        kw_block_pattern = re.compile(
            r'<w:p>\s*<w:pPr>\s*<w:pStyle w:val="BodyText"/>\s*</w:pPr>\s*'
            r'(<w:r>\s*<w:rPr>\s*<w:rFonts w:hint="eastAsia"/>\s*<w:b/>\s*<w:bCs/>\s*</w:rPr>\s*'
            r'<w:t xml:space="preserve">关键词：</w:t>\s*</w:r>)',
            re.DOTALL
        )
        new_content = kw_block_pattern.sub(
            r'<w:p><w:pPr><w:pStyle w:val="Abstract"/><w:ind w:firstLine="0" w:firstLineChars="0"/></w:pPr>'
            r'<w:r><w:rPr><w:rFonts w:ascii="SimHei" w:hAnsi="SimHei" w:eastAsia="SimHei" w:cs="SimHei" w:hint="eastAsia"/><w:b/><w:bCs/></w:rPr>'
            r'<w:t xml:space="preserve">关键词：</w:t></w:r>',
            new_content
        )

    doc_path.write_text(new_content, encoding="utf-8")
    print(f"  封面重组完成: 赛事抬头、主标题「{paper_title[:20]}...」、"
          f"{'副标题' if sub_title else '无副标题'}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python3 step0_rebuild_cover.py <unpacked_dir>")
        sys.exit(1)
    rebuild_cover(Path(sys.argv[1]))
