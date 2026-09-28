# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具名称：Claude Code；版本/型号：Claude Opus 5.5；开发机构：Anthropic；版本颁布日期：2026 年 9 月 22 日
# 由 LaTeX 源生成 Word 版论文。
#   1. 用 main.aux 把图、表、公式、算法、命题编号和交叉引用替换成实际数字，用 numbers.tex 展开 \V{} 宏；
#   2. pandoc 把正文转成 docx（公式为 Word 原生公式）；TikZ 过程图与算法框事先渲染为 PNG（docx_build/）；
#   3. 套官方 Word 模板（附件3）的封面与摘要页，按附件2 设置字体、字号、行距、页码。
# 用法：先在 paper/tex 下编译 main.tex（生成 main.aux），再运行
#   python3.11 src/make_docx.py  →  paper/A题论文_Word版.docx
import copy, io, os, re, subprocess, sys
import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Cm

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
TEX = os.path.join(ROOT, 'paper', 'tex')
FIG = os.path.join(ROOT, 'paper', 'fig')
BUILD = os.path.join(ROOT, 'paper', 'docx_build')
TEMPLATE = os.path.join(BUILD, 'template.docx')
OUT = os.path.join(ROOT, 'paper', 'A题论文_Word版.docx')
TITLE = '面向共享带宽多核 NPU 的结构自适应切图调度与缓存时序分析'
BODY_FILES = ['s1_restate', 's2_analysis', 's3_assume', 's4_symbols', 's5_overview', 's5_p1', 's5_p2', 's5_p3',
              's6_check', 's7_eval']

# ------------------------------------------------------------------ 编号与数字宏
aux = open(os.path.join(TEX, 'main.aux'), encoding='utf-8').read()
LABEL = {m.group(1): m.group(2) for m in re.finditer(r'\\newlabel\{([^}]+)\}\{\{([^}]*)\}', aux)}
BIB = {m.group(1): m.group(2) for m in re.finditer(r'\\bibcite\{([^}]+)\}\{\{([^}]*)\}', aux)}
VAL = {}
for line in open(os.path.join(TEX, 'numbers.tex'), encoding='utf-8'):
    m = re.match(r'\\expandafter\\def\\csname v@(.+?)\\endcsname\{(.*)\}\s*$', line)
    if m:
        VAL[m.group(1)] = m.group(2)


def braced(s, i):
    """s[i] == '{'，返回 (内容, 右括号之后的位置)。"""
    depth, j = 0, i
    while j < len(s):
        if s[j] == '{' and s[j - 1] != '\\':
            depth += 1
        elif s[j] == '}' and s[j - 1] != '\\':
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    raise ValueError('括号不匹配：' + s[i:i + 60])


def cmd_arg(s, name):
    """找到第一个 \\name{...}，返回 (起点, 内容, 终点)；没有则 None。"""
    m = re.search(re.escape('\\' + name) + r'\{', s)
    if not m:
        return None
    body, end = braced(s, m.end() - 1)
    return m.start(), body, end


def strip_comments(s):
    return '\n'.join(re.sub(r'(?<!\\)%.*$', '', l) for l in s.split('\n'))


def fig_png(name):
    for d in (FIG, os.path.join(BUILD, 'tikz')):
        p = os.path.join(d, name + '.png')
        if os.path.exists(p):
            return p
    raise FileNotFoundError(name)


def conv_figure(block):
    """一个 figure 环境 → 一个或多个 pandoc 可读的 figure（标题前加“图 N”）。"""
    parts = re.findall(r'\\begin\{minipage\}.*?\\end\{minipage\}', block, re.S) or [block]
    out = []
    for p in parts:
        lab = re.search(r'\\label\{([^}]+)\}', p)
        g = re.search(r'\\includegraphics(\[[^\]]*\])?\{([^}]+)\}', p)
        t = re.search(r'\\input\{tikz/([^}]+)\}', p)
        path = fig_png(g.group(2)) if g else fig_png(t.group(1))
        w = re.search(r'width=([0-9.]*)\\textwidth', g.group(1) or '') if g else None
        frac = float(w.group(1) or 1) if w else 1.0
        if len(parts) > 1:
            frac = 0.62
        c = cmd_arg(p, 'caption')
        cap = c[1] if c else ''
        num = LABEL.get(lab.group(1), '?') if lab else '?'
        out.append('\\begin{figure}\n\\centering\n\\includegraphics[width=%.2f\\textwidth]{%s}\n\\caption{图 %s\\quad %s}\n\\end{figure}\n'
                   % (frac, path, num, cap))
    return '\n'.join(out)


def conv_longtable(s):
    """longtable → table + tabular，去掉重复表头，标题前加“表 N”。"""
    def one(m):
        spec, body = m.group(1), m.group(2)
        c = cmd_arg(body, 'caption')
        cap = c[1]
        body = body[c[2]:]
        lab = re.search(r'\\label\{([^}]+)\}', body)
        num = LABEL.get(lab.group(1), '?') if lab else '?'
        body = re.sub(r'^\s*\\label\{[^}]+\}\s*\\\\', '', body)
        if '\\endhead' in body:
            a = body.index('\\endfirsthead')
            b = body.index('\\endhead') + len('\\endhead')
            body = body[:a] + body[b:]
        body = re.sub(r'\\bottomrule\s*\\endfoot', '', body)
        body = body.replace('\\endlastfoot', '').replace('\\endfoot', '')
        if '\\bottomrule' not in body:
            body = body.rstrip() + '\n\\bottomrule\n'
        return ('\\begin{table}\n\\caption{表 %s\\quad %s}\n\\begin{tabular}{%s}%s\\end{tabular}\n\\end{table}\n'
                % (num, cap, spec, body))
    out, pos = [], 0
    while True:
        i = s.find('\\begin{longtable}', pos)
        if i < 0:
            out.append(s[pos:])
            return ''.join(out)
        spec, j = braced(s, i + len('\\begin{longtable}'))
        k = s.index('\\end{longtable}', j)
        class M:
            def __init__(self, a, b): self.g = (None, a, b)
            def group(self, n): return self.g[n]
        out.append(s[pos:i]); out.append(one(M(spec, s[j:k])))
        pos = k + len('\\end{longtable}')


def conv_table(block):
    c = cmd_arg(block, 'caption')
    lab = re.search(r'\\label\{([^}]+)\}', block)
    num = LABEL.get(lab.group(1), '?') if lab else '?'
    block = block[:c[0]] + '\\caption{表 %s\\quad %s}' % (num, c[1]) + block[c[2]:]
    block = re.sub(r'\\resizebox\{\\textwidth\}\{!\}\{', '', block)
    block = block.replace('\\end{tabular}}', '\\end{tabular}')
    block = re.sub(r'\\begin\{tabularx\}\{\\textwidth\}\{([^}]*)\}', lambda m: '\\begin{tabular}{' + m.group(1).replace('X', 'l') + '}', block)
    return block.replace('\\end{tabularx}', '\\end{tabular}')


def convert(s):
    s = strip_comments(s)
    for _ in range(3):
        s = re.sub(r'\\V\{([^}]+)\}', lambda m: VAL.get(m.group(1), '??' + m.group(1)), s)
    # 源码清单
    def lst(m):
        title = re.search(r'title=\{\\small\s*(.*)\}\s*$', m.group(1)).group(1)
        code = open(os.path.join(TEX, m.group(2)), encoding='utf-8').read()
        return '\n\n\\textbf{%s}\n\n\\begin{verbatim}\n%s\\end{verbatim}\n\n' % (title, code)
    s = re.sub(r'\\lstinputlisting\[(.*?)\]\{([^}]+)\}', lst, s, flags=re.S)
    s = re.sub(r'\\input\{(tables/[^}]+)\}', lambda m: open(os.path.join(TEX, m.group(1) + '.tex'), encoding='utf-8').read(), s)
    s = conv_longtable(s)
    s = re.sub(r'\\begin\{figure\}\[H\](.*?)\\end\{figure\}', lambda m: conv_figure(m.group(1)), s, flags=re.S)
    s = re.sub(r'\\begin\{table\}\[H\](.*?)\\end\{table\}', lambda m: conv_table('\\begin{table}' + m.group(1) + '\\end{table}'), s, flags=re.S)
    # 算法框 → 预渲染图片（图片内含“算法 N”标题）
    def alg(m):
        lab = re.search(r'\\label\{(alg:[^}]+)\}', m.group(1)).group(1)
        return '\\begin{figure}\n\\centering\n\\includegraphics[width=\\textwidth]{%s}\n\\end{figure}\n' % os.path.join(BUILD, 'alg', lab.replace(':', '_') + '.png')
    s = re.sub(r'\\begin\{algorithm\}\[H\](.*?)\\end\{algorithm\}', alg, s, flags=re.S)
    # 公式：编号写进公式末尾
    def eq(m):
        body = m.group(1)
        lab = re.search(r'\\label\{([^}]+)\}', body)
        num = LABEL.get(lab.group(1), '?') if lab else ''
        body = re.sub(r'\\label\{[^}]+\}', '', body).strip()
        body = re.sub(r'\\begin\{aligned\}(.*?)\\end\{aligned\}',
                      lambda a: '\\begin{array}{l}' + a.group(1).replace('&', '\\ ') + '\\end{array}', body, flags=re.S)
        return '\\[\n%s\n\\]〔EQ%s〕' % (body, num)
    s = re.sub(r'\\begin\{equation\}(.*?)\\end\{equation\}', eq, s, flags=re.S)
    # 命题与证明
    s = re.sub(r'\\begin\{proposition\}\\label\{([^}]+)\}', lambda m: '\\textbf{命题 %s}\\quad ' % LABEL.get(m.group(1), '?'), s)
    s = s.replace('\\end{proposition}', '').replace('\\begin{proof}', '\\textbf{证明}\\quad ').replace('\\end{proof}', '')
    # 交叉引用与文献
    s = re.sub(r'\\eqref\{([^}]+)\}', lambda m: '(%s)' % LABEL.get(m.group(1), '?'), s)
    s = re.sub(r'\\ref\{([^}]+)\}', lambda m: LABEL.get(m.group(1), '?'), s)
    s = re.sub(r'\\cite\{([^}]+)\}', lambda m: '\\textsuperscript{[%s]}' % ','.join(BIB.get(k.strip(), '?') for k in m.group(1).split(',')), s)
    s = re.sub(r'\\label\{[^}]+\}', '', s)
    # 自定义命令
    s = re.sub(r'\\Oe(?![a-zA-Z])', r'{O^{\\ast}}', s)
    s = re.sub(r'\\sg(?![a-zA-Z])', r'\\sigma', s)
    s = re.sub(r'\\core(?![a-zA-Z])', r'\\kappa', s)
    s = re.sub(r'\\ind(?![a-zA-Z])', r'\\mathbf{1}', s)
    s = re.sub(r'\\argmin(?![a-zA-Z])', r'\\mathop{\\mathrm{arg\\,min}}', s)
    s = re.sub(r'\\argmax(?![a-zA-Z])', r'\\mathop{\\mathrm{arg\\,max}}', s)
    s = re.sub(r'\\multirow\{[^}]*\}\{[^}]*\}\{([^{}]*)\}', r'\1', s)
    s = re.sub(r'\\cmidrule(\([^)]*\))?\{[^}]*\}', '', s)
    for pat in (r'\\begin\{footnotesize\}', r'\\end\{footnotesize\}', r'\\renewcommand\\arraystretch\{[^}]*\}',
                r'\\setlength\{\\tabcolsep\}\{[^}]*\}', r'\\noindent', r'\\centering'):
        s = re.sub(pat, '', s)
    s = s.replace('\\LaTeX{}', 'LaTeX')
    return s


def refs_and_appendix():
    r = open(os.path.join(TEX, 'sections', 'refs.tex'), encoding='utf-8').read()
    items = re.findall(r'\\bibitem\{([^}]+)\}\s*(.*)', r)
    out = ['\\section*{参考文献}']
    for key, text in items:
        out.append('[%s] %s\n' % (BIB.get(key, '?'), text.strip()))
    a = open(os.path.join(TEX, 'sections', 'appendix.tex'), encoding='utf-8').read()
    letters = iter('ABCDEFGH')
    a = re.sub(r'\\section\{([^}]*)\}', lambda m: '\\section*{附录 %s\\quad %s}' % (next(letters), m.group(1)), a)
    return '\n\n'.join(out) + '\n\n' + a


def build_tex():
    body = '\n\n'.join(open(os.path.join(TEX, 'sections', f + '.tex'), encoding='utf-8').read() for f in BODY_FILES)
    body = convert(body + '\n\n' + refs_and_appendix())
    ab = open(os.path.join(TEX, 'sections', 'abstract.tex'), encoding='utf-8').read()
    kw = cmd_arg(ab, 'keywords')
    keywords = re.sub(r'\\quad', '；', kw[1]).strip('； ')
    ab = ab[:kw[0]]
    ab = ab.replace('\\begin{abstract}', '').replace('\\end{abstract}', '')
    ab = convert(ab)
    doc = '\\documentclass{article}\n\\usepackage{amsmath}\n\\begin{document}\n%s\n\\end{document}\n'
    open(os.path.join(BUILD, 'body.tex'), 'w', encoding='utf-8').write(doc % body)
    open(os.path.join(BUILD, 'abstract.tex'), 'w', encoding='utf-8').write(doc % ab)
    return keywords


# ------------------------------------------------------------------ Word 样式
def set_font(style_or_run_font, east='宋体', west='Times New Roman', size=None, bold=None):
    f = style_or_run_font
    f.name = west
    rpr = f.element.get_or_add_rPr() if hasattr(f, 'element') else None
    if size is not None:
        f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    return rpr


def east_asia(el_rpr, east, west='Times New Roman'):
    rfonts = el_rpr.find(qn('w:rFonts'))
    if rfonts is None:
        rfonts = OxmlElement('w:rFonts')
        el_rpr.insert(0, rfonts)
    for k in ('w:ascii', 'w:hAnsi', 'w:cs'):
        rfonts.set(qn(k), west)
    rfonts.set(qn('w:eastAsia'), east)
    for k in ('w:asciiTheme', 'w:hAnsiTheme', 'w:eastAsiaTheme', 'w:cstheme'):
        if rfonts.get(qn(k)) is not None:
            del rfonts.attrib[qn(k)]


def style_fmt(st, east, size, bold=False, align=None, first_indent=False, color_black=True, italic=False):
    st.font.size = Pt(size)
    st.font.bold = bold
    st.font.italic = italic
    if color_black:
        st.font.color.rgb = docx.shared.RGBColor(0, 0, 0)
    east_asia(st.element.get_or_add_rPr(), east)
    pf = st.paragraph_format
    pf.line_spacing = 1.0
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    if align is not None:
        pf.alignment = align
    ppr = st.element.get_or_add_pPr()
    ind = ppr.find(qn('w:ind'))
    if first_indent:
        if ind is None:
            ind = OxmlElement('w:ind'); ppr.append(ind)
        ind.set(qn('w:firstLineChars'), '200')
        ind.set(qn('w:firstLine'), '480')
    else:
        if ind is None:
            ind = OxmlElement('w:ind'); ppr.append(ind)
        ind.set(qn('w:firstLineChars'), '0')
        ind.set(qn('w:firstLine'), '0')


def make_reference():
    ref = os.path.join(BUILD, 'reference.docx')
    with open(ref, 'wb') as f:
        f.write(subprocess.run(['pandoc', '--print-default-data-file', 'reference.docx'], capture_output=True, check=True).stdout)
    d = docx.Document(ref)
    S = d.styles
    for name in ('Normal', 'Body Text', 'First Paragraph', 'Compact'):
        if name in S:
            style_fmt(S[name], '宋体', 12, first_indent=name in ('Body Text', 'First Paragraph'))
    style_fmt(S['Heading 1'], '黑体', 14, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER)
    style_fmt(S['Heading 2'], '黑体', 12, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT)
    style_fmt(S['Heading 3'], '黑体', 12, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT)
    for h in ('Heading 1', 'Heading 2', 'Heading 3'):
        S[h].paragraph_format.space_before = Pt(6)
        S[h].paragraph_format.space_after = Pt(6)
        S[h].paragraph_format.keep_with_next = True
    for name in ('Image Caption', 'Table Caption', 'Caption'):
        if name in S:
            style_fmt(S[name], '宋体', 10.5, align=WD_ALIGN_PARAGRAPH.CENTER)
            S[name].paragraph_format.space_after = Pt(6)
    if 'Table Caption' in S:
        S['Table Caption'].paragraph_format.space_before = Pt(6)
        S['Table Caption'].paragraph_format.space_after = Pt(3)
    for name in ('Captioned Figure', 'Figure'):
        if name in S:
            S[name].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for name in ('Source Code',):
        if name in S:
            style_fmt(S[name], '宋体', 9)
    if 'Verbatim Char' in S:
        S['Verbatim Char'].font.size = Pt(9)
        east_asia(S['Verbatim Char'].element.get_or_add_rPr(), '宋体', 'Menlo')
    d.save(ref)
    return ref


def pandoc(name, ref):
    subprocess.run(['pandoc', os.path.join(BUILD, name + '.tex'), '-f', 'latex', '-o', os.path.join(BUILD, name + '.docx'),
                    '--reference-doc', ref] + (['--number-sections'] if name == 'body' else []),
                   check=True, cwd=BUILD)
    return docx.Document(os.path.join(BUILD, name + '.docx'))


# ------------------------------------------------------------------ 组装
def para_xml(text, east='宋体', size=12, bold=False, align='center', page_break_before=False):
    p = OxmlElement('w:p')
    ppr = OxmlElement('w:pPr')
    if page_break_before:
        ppr.append(OxmlElement('w:pageBreakBefore'))
    jc = OxmlElement('w:jc'); jc.set(qn('w:val'), align); ppr.append(jc)
    p.append(ppr)
    r = OxmlElement('w:r'); rpr = OxmlElement('w:rPr')
    east_asia(rpr, east)
    if bold:
        rpr.append(OxmlElement('w:b'))
    sz = OxmlElement('w:sz'); sz.set(qn('w:val'), str(int(size * 2))); rpr.append(sz)
    r.append(rpr)
    t = OxmlElement('w:t'); t.text = text; t.set(qn('xml:space'), 'preserve'); r.append(t)
    p.append(r)
    return p


def page_break():
    p = OxmlElement('w:p'); r = OxmlElement('w:r'); br = OxmlElement('w:br'); br.set(qn('w:type'), 'page')
    r.append(br); p.append(r); return p


def toc_paragraphs():
    title = para_xml('目  录', east='黑体', size=14)
    p = OxmlElement('w:p')
    def fld(kind, text=None):
        r = OxmlElement('w:r')
        if kind == 'instr':
            it = OxmlElement('w:instrText'); it.set(qn('xml:space'), 'preserve'); it.text = text; r.append(it)
        else:
            fc = OxmlElement('w:fldChar'); fc.set(qn('w:fldCharType'), kind)
            if kind == 'begin':
                fc.set(qn('w:dirty'), 'true')
            r.append(fc)
        return r
    p.append(fld('begin')); p.append(fld('instr', ' TOC \\o "1-3" \\h \\z \\u ')); p.append(fld('separate'))
    r = OxmlElement('w:r'); t = OxmlElement('w:t'); t.text = '（在 Word 中右键此处选择“更新域”生成目录）'; r.append(t); p.append(r)
    p.append(fld('end'))
    return [title, p]


def copy_with_images(el, src_doc, dst_doc):
    el = copy.deepcopy(el)
    for node in el.iter():
        for attr in (qn('r:embed'), qn('r:id')):
            rid = node.get(attr)
            if rid and rid in src_doc.part.rels and 'image' in src_doc.part.rels[rid].reltype:
                blob = src_doc.part.rels[rid].target_part.blob
                new_rid, _ = dst_doc.part.get_or_add_image(io.BytesIO(blob))
                node.set(attr, new_rid)
    return el


ORDER = {
    'pPr': 'pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd tabs '
           'suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi adjustRightInd '
           'snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection textAlignment '
           'textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange',
    'rPr': 'rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow emboss imprint noProof snapToGrid '
           'vanish webHidden color spacing w kern position sz szCs highlight u effect bdr shd fitText vertAlign rtl cs '
           'em lang eastAsianLayout specVanish oMath',
    'tblPr': 'tblStyle tblpPr tblOverlap bidiVisual tblStyleRowBandSize tblStyleColBandSize tblW jc tblCellSpacing '
             'tblInd tblBorders shd tblLayout tblCellMar tblLook tblCaption tblDescription',
    'trPr': 'cnfStyle divId gridBefore gridAfter wBefore wAfter cantSplit trHeight tblHeader tblCellSpacing jc hidden',
    'tcPr': 'cnfStyle tcW gridSpan hMerge vMerge tcBorders shd noWrap tcMar textDirection tcFitText vAlign hideMark',
}


def sort_props(root):
    """按 OOXML 规定的子元素顺序重排属性节点，并去掉重复的同名子元素（保留最后一个）。"""
    W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    for tag, seq in ORDER.items():
        rank = {n: i for i, n in enumerate(seq.split())}
        for el in root.iter(W + tag):
            kids = list(el)
            seen = {}
            for k in kids:
                seen[k.tag] = k
            uniq = [k for k in kids if seen[k.tag] is k]
            uniq.sort(key=lambda k: rank.get(k.tag.replace(W, ''), 999))
            for k in kids:
                el.remove(k)
            for k in uniq:
                el.append(k)


def number_equations(doc, text_w):
    """公式单独成行：中心制表位放公式、右制表位放编号；公式后紧接的文字不缩进。"""
    M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
    for mp in list(doc.element.body.iter('{%s}oMathPara' % M)):
        p = mp.getparent()
        if p.tag != qn('w:p'):
            continue
        nxt = p.getnext()
        num = None
        if nxt is not None and nxt.tag == qn('w:p'):
            ts = nxt.findall('.//' + qn('w:t'))
            if ts and ts[0].text and ts[0].text.startswith('〔EQ'):
                m = re.match(r'〔EQ([^〕]*)〕', ts[0].text)
                num = m.group(1)
                ts[0].text = ts[0].text[m.end():].lstrip()
                if not ''.join(t.text or '' for t in ts).strip() and not nxt.findall('.//{%s}oMath' % M):
                    nxt.getparent().remove(nxt)
                else:
                    ppr = nxt.find(qn('w:pPr'))
                    if ppr is None:
                        ppr = OxmlElement('w:pPr'); nxt.insert(0, ppr)
                    ind = OxmlElement('w:ind'); ind.set(qn('w:firstLine'), '0'); ind.set(qn('w:firstLineChars'), '0')
                    ppr.append(ind)
        ppr = p.find(qn('w:pPr'))
        if ppr is None:
            ppr = OxmlElement('w:pPr'); p.insert(0, ppr)
        tabs = OxmlElement('w:tabs')
        for val, pos in (('center', text_w // 2), ('right', text_w)):
            t = OxmlElement('w:tab'); t.set(qn('w:val'), val); t.set(qn('w:pos'), str(pos)); tabs.append(t)
        ppr.append(tabs)
        ind = OxmlElement('w:ind'); ind.set(qn('w:firstLine'), '0'); ind.set(qn('w:firstLineChars'), '0'); ppr.append(ind)
        om = mp.find('{%s}oMath' % M)
        idx = list(p).index(mp)
        p.remove(mp)
        items = []
        r = OxmlElement('w:r'); r.append(OxmlElement('w:tab')); items.append(r)
        items.append(om)
        if num:
            r = OxmlElement('w:r'); r.append(OxmlElement('w:tab')); items.append(r)
            r = OxmlElement('w:r'); t = OxmlElement('w:t'); t.text = '(%s)' % num; r.append(t); items.append(r)
        for k, it in enumerate(items):
            p.insert(idx + k, it)


def fit_tables(doc, text_w):
    """按各列内容长度分配列宽（公式按字符数估计），表宽为版心宽。"""
    M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
    for tb in doc.tables:
        tbl = tb._tbl
        ncol = len(tbl.tblGrid.findall(qn('w:gridCol')))
        need = [1.0] * ncol
        for tr in tbl.findall(qn('w:tr')):
            tcs = tr.findall(qn('w:tc'))
            if len(tcs) != ncol:
                continue
            for j, tc in enumerate(tcs):
                txt = ''.join(t.text or '' for t in tc.iter(qn('w:t'))) + ''.join(t.text or '' for t in tc.iter('{%s}t' % M))
                w = sum(2 if ord(ch) > 0x2E80 else 1 for ch in txt)
                need[j] = max(need[j], min(w, 60))
        first = ''.join(t.text or '' for t in tbl.find(qn('w:tr')).iter(qn('w:t')))
        if ncol == 3 and first.startswith('类别'):
            need = [14, 24, 62]
        tot = sum(need)
        widths = [max(int(text_w * n / tot), 500) for n in need]
        scale = text_w / sum(widths)
        widths = [int(w * scale) for w in widths]
        for gc, w in zip(tbl.tblGrid.findall(qn('w:gridCol')), widths):
            gc.set(qn('w:w'), str(w))
        tpr = tbl.tblPr
        tw = tpr.find(qn('w:tblW'))
        if tw is None:
            tw = OxmlElement('w:tblW'); tpr.append(tw)
        tw.set(qn('w:type'), 'dxa'); tw.set(qn('w:w'), str(text_w))
        lay = OxmlElement('w:tblLayout'); lay.set(qn('w:type'), 'fixed'); tpr.append(lay)
        mar = OxmlElement('w:tblCellMar')
        for side in ('left', 'right'):
            e = OxmlElement('w:' + side); e.set(qn('w:w'), '40' if ncol >= 7 else '80'); e.set(qn('w:type'), 'dxa'); mar.append(e)
        tpr.append(mar)
        tbl.set('data-ncol', str(ncol))
        for tr in tbl.findall(qn('w:tr')):
            tcs = tr.findall(qn('w:tc'))
            if len(tcs) != ncol:
                continue
            for tc, w in zip(tcs, widths):
                tcpr = tc.find(qn('w:tcPr'))
                if tcpr is None:
                    tcpr = OxmlElement('w:tcPr'); tc.insert(0, tcpr)
                for old in tcpr.findall(qn('w:tcW')):
                    tcpr.remove(old)
                cw = OxmlElement('w:tcW'); cw.set(qn('w:w'), str(w)); cw.set(qn('w:type'), 'dxa'); tcpr.insert(0, cw)


def assemble(keywords):
    ref = make_reference()
    body = pandoc('body', ref)
    abst = pandoc('abstract', ref)
    tpl = docx.Document(TEMPLATE)

    # 页面：沿用官方模板的纸张与页边距
    ts = tpl.sections[0]
    for s in body.sections:
        s.page_width, s.page_height = ts.page_width, ts.page_height
        s.top_margin, s.bottom_margin, s.left_margin, s.right_margin = ts.top_margin, ts.bottom_margin, ts.left_margin, ts.right_margin
        s.header_distance, s.footer_distance = ts.header_distance, ts.footer_distance

    tbody = list(tpl.element.body)
    tparas = [e for e in tbody if e.tag == qn('w:p')]
    second_head = tparas[13]                         # 摘要页的“中国研究生创新实践系列大赛”
    cover = tbody[:tbody.index(second_head)]
    head2 = tbody[tbody.index(second_head):tbody.index(tparas[19])]   # 抬头 + 题目行
    zy, gjc = tparas[19], tparas[23]

    B = body.element.body
    first = B[0]
    def ins(el):
        first.addprevious(el)

    for e in cover:
        if e.tag in (qn('w:p'), qn('w:tbl')):
            ins(copy_with_images(e, tpl, body))
    # 封面单独成节，不设页脚
    sp = OxmlElement('w:p'); ppr = OxmlElement('w:pPr')
    sect = copy.deepcopy(B.find(qn('w:sectPr')))
    for fr in sect.findall(qn('w:footerReference')) + sect.findall(qn('w:headerReference')):
        sect.remove(fr)
    typ = sect.find(qn('w:type'))
    if typ is None:
        typ = OxmlElement('w:type'); sect.insert(0, typ)
    typ.set(qn('w:val'), 'nextPage')
    ppr.append(sect); sp.append(ppr); ins(sp)

    for e in head2:
        e2 = copy_with_images(e, tpl, body)
        txt = ''.join(t.text or '' for t in e2.iter(qn('w:t')))
        if '题 目' in txt:
            runs = e2.findall(qn('w:r'))
            for r in runs:
                t = r.find(qn('w:t'))
                if t is not None and '_' in (t.text or ''):
                    t.text = TITLE
                    rpr = r.find(qn('w:rPr'))
                    if rpr is None:
                        rpr = OxmlElement('w:rPr'); r.insert(0, rpr)
                    for child in list(rpr):
                        if child.tag in (qn('w:u'), qn('w:sz'), qn('w:szCs'), qn('w:rFonts')):
                            rpr.remove(child)
                    east_asia(rpr, '黑体')
                    sz = OxmlElement('w:sz'); sz.set(qn('w:val'), '32'); rpr.append(sz)
        ins(e2)
    ins(copy.deepcopy(zy))
    for p in abst.element.body:
        if p.tag == qn('w:p'):
            ins(copy.deepcopy(p))
    kw = copy.deepcopy(gjc)
    r = OxmlElement('w:r'); rpr = OxmlElement('w:rPr'); east_asia(rpr, '宋体')
    sz = OxmlElement('w:sz'); sz.set(qn('w:val'), '24'); rpr.append(sz); r.append(rpr)
    t = OxmlElement('w:t'); t.text = keywords; t.set(qn('xml:space'), 'preserve'); r.append(t)
    kw.append(r)
    ins(kw)
    ins(page_break())
    for e in toc_paragraphs():
        ins(e)
    ins(page_break())

    # 页码：从摘要页开始，页脚居中
    sec = body.sections[-1]
    sec.footer.is_linked_to_previous = False
    fp = sec.footer.paragraphs[0] if sec.footer.paragraphs else sec.footer.add_paragraph()
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for kind, text in (('begin', None), ('instr', ' PAGE '), ('end', None)):
        r = fp.add_run()
        if kind == 'instr':
            it = OxmlElement('w:instrText'); it.set(qn('xml:space'), 'preserve'); it.text = text; r._r.append(it)
        else:
            fc = OxmlElement('w:fldChar'); fc.set(qn('w:fldCharType'), kind); r._r.append(fc)
        r.font.size = Pt(10.5)
    pg = sec._sectPr.find(qn('w:pgNumType'))
    if pg is None:
        pg = OxmlElement('w:pgNumType'); sec._sectPr.append(pg)
    pg.set(qn('w:start'), '1')
    sec.header.is_linked_to_previous = False                      # 不设页眉

    text_w = int((body.sections[-1].page_width - body.sections[-1].left_margin - body.sections[-1].right_margin) / 635)
    number_equations(body, text_w)
    fit_tables(body, text_w)
    # 表格：三线表、五号字、居中
    for tb in body.tables:
        tbl = tb._tbl
        tpr = tbl.tblPr
        for old in tpr.findall(qn('w:tblBorders')):
            tpr.remove(old)
        bd = OxmlElement('w:tblBorders')
        for side, w in (('top', '12'), ('bottom', '12')):
            e = OxmlElement('w:' + side); e.set(qn('w:val'), 'single'); e.set(qn('w:sz'), w); e.set(qn('w:color'), '000000')
            bd.append(e)
        tpr.append(bd)
        jc = tpr.find(qn('w:jc'))
        if jc is None:
            jc = OxmlElement('w:jc'); tpr.append(jc)
        jc.set(qn('w:val'), 'center')
        rows = tb.rows
        if rows:
            hdr_n = 1
            for cell in rows[hdr_n - 1].cells:
                tcpr = cell._tc.get_or_add_tcPr()
                b = OxmlElement('w:tcBorders'); e = OxmlElement('w:bottom')
                e.set(qn('w:val'), 'single'); e.set(qn('w:sz'), '6'); e.set(qn('w:color'), '000000'); b.append(e); tcpr.append(b)
        for row in rows:
            trpr = row._tr.get_or_add_trPr()
            trpr.append(OxmlElement('w:cantSplit'))
            small = int(tbl.get('data-ncol', '0')) >= 7
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.first_line_indent = Pt(0)
                    p._p.get_or_add_pPr().find(qn('w:ind')).set(qn('w:firstLineChars'), '0')
                    p.paragraph_format.line_spacing = 1.0
                    for r in p.runs:
                        r.font.size = Pt(8 if small else 10.5)
    # 图片段落居中、去首行缩进
    for p in body.paragraphs:
        if p._p.xpath('.//w:drawing'):
            p.paragraph_format.first_line_indent = Pt(0)
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # 打开时提示更新目录域
    st = body.settings.element
    uf = st.find(qn('w:updateFields'))
    if uf is None:
        uf = OxmlElement('w:updateFields'); st.append(uf)
    uf.set(qn('w:val'), 'true')
    for tb in body.tables:
        if tb._tbl.get('data-ncol') is not None:
            del tb._tbl.attrib['data-ncol']
    sort_props(body.element)
    for part in (body.sections[-1].footer.part,):
        sort_props(part.element)
    body.save(OUT)
    print('写出', OUT)


if __name__ == '__main__':
    kw = build_tex()
    assemble(kw)
