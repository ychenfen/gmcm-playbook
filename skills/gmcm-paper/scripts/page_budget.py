# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方公布为准）
"""论文篇幅体检：页数、图、表、编号公式，对照 2025 年 21 篇优秀论文和本队目标。

用法:
  python3 page_budget.py 论文.pdf
  python3 page_budget.py 论文.pdf --questions 4     按问题数给出每问页数预算

Word 写的先导出 PDF 再查。取文本依次尝试 pdftotext（poppler）、PyMuPDF、pypdf，装一个即可：
  Mac: brew install poppler      Windows/通用: pip install pymupdf

口径：「正文页」= 摘要页起、参考文献前一页止（含摘要和目录，不含封面、参考文献、附录），与 2025 统计同口径。
图、表按行首的「图 x」「表 x」图题计数，公式按行尾的「(x)」「(x-y)」编号计数；公式做成图片或不编号的数不到。
"""
import re, sys, shutil, subprocess

# 2025 年 21 篇优秀论文实测（A4 题 4 篇、B 3、C 5、D 2、E 3、F 4）
REF_2025 = {
    '全文页数': (46, 68, 76, 96, 182),          # 最小、下四分位、中位、上四分位、最大
    '正文页数': (34, 40.5, 55, 67.5, 101),      # 摘要页至参考文献前
    '图': (9, 19, 30, 41, 107),
    '表': (2, 5, 12, 15, 29),
}
TARGET = {'正文页数': (45, 55, 70), '图': (20, 30, 45), '表': (8, 12, 20), '编号公式': (40, 60, 150)}   # 下限、目标、上限


def pages_text(pdf):
    if shutil.which('pdftotext'):
        n = int(re.search(r'Pages:\s+(\d+)', subprocess.run(['pdfinfo', pdf], capture_output=True, text=True).stdout).group(1))
        return [subprocess.run(['pdftotext', '-f', str(i), '-l', str(i), '-layout', pdf, '-'],
                               capture_output=True, text=True).stdout for i in range(1, n + 1)]
    try:
        import fitz
        return [p.get_text() for p in fitz.open(pdf)]
    except ImportError:
        pass
    try:
        from pypdf import PdfReader
        return [p.extract_text() or '' for p in PdfReader(pdf).pages]
    except ImportError:
        sys.exit('需要 pdftotext（brew install poppler）或 pip install pymupdf / pypdf 之一')


def analyse(pages):
    n = len(pages)
    kw = next((i for i, t in enumerate(pages, 1) if re.search(r'关\s*键\s*词', t)), 1)
    ref, cut = None, 0
    for i, t in enumerate(pages, 1):
        m = re.search(r'^\s*[\d.、一二三四五六七八九十]*\s*参\s*考\s*文\s*献\s*$', t, re.M)
        if i > kw and m and re.search(r'^\s*\[\s*1\s*\]|^\s*1[.、]\s', t[m.end():], re.M) and not re.search(r'\.{6,}', t):
            ref, cut = i, m.start()
            break
    abs_start = kw
    for i in range(kw, 0, -1):                              # 摘要跨两页时，从含「摘要」的那页算起
        if re.search(r'摘\s*要', pages[i - 1]):
            abs_start = i
            break
    end = (ref - 1) if ref else n
    body = '\n'.join(pages[abs_start - 1:end]) + ('\n' + pages[ref - 1][:cut] if ref else '')   # 参考文献页标题前的正文也算
    figs = set(re.findall(r'^\s*图\s*(\d+(?:[.\-]\d+)*)\s', body, re.M))
    tabs = set(re.findall(r'^\s*表\s*(\d+(?:[.\-]\d+)*)\s', body, re.M))
    eqs = set(re.findall(r'[(（]\s*(\d+(?:[.\-]\d+)*)\s*[)）]\s*$', body, re.M))
    return dict(total=n, abstract=abs_start, ref=ref, body=end - abs_start + 1,
                figs=len(figs), tabs=len(tabs), eqs=len(eqs))


def verdict(k, v):
    lo, tgt, hi = TARGET[k]
    if v < lo:
        return f'偏少，至少补到 {lo}（目标 {tgt}）'
    if v > hi:
        return f'偏多，检查有没有凑数的内容（上限参考 {hi}）'
    return '在目标区间内'


def main(argv):
    if not argv:
        print(__doc__); return 2
    q = None
    if '--questions' in argv:
        i = argv.index('--questions'); q = int(argv[i + 1]); argv = argv[:i] + argv[i + 2:]
    r = analyse(pages_text(argv[0]))
    print(f'== {argv[0]}')
    print(f'  全文 {r["total"]} 页；摘要从第 {r["abstract"]} 页开始；'
          + (f'参考文献从第 {r["ref"]} 页开始' if r['ref'] else '没识别到参考文献页（按全文算到最后一页）'))
    rows = [('正文页数', r['body']), ('图', r['figs']), ('表', r['tabs']), ('编号公式', r['eqs'])]
    print(f'\n  {"项目":<6}{"本文":>6}   {"2025 优秀论文（下四分位/中位/上四分位）":<28}  结论')
    for k, v in rows:
        ref = REF_2025.get(k)
        refs = f'{ref[1]}/{ref[2]}/{ref[3]}' if ref else '—（公式常做成图片，不可比）'
        print(f'  {k:<6}{v:>6}   {refs:<34}  {verdict(k, v)}')
    if q:
        tgt = TARGET['正文页数'][1]
        core = tgt - 12                     # 摘要 2 + 重述/分析 4 + 假设符号 2 + 评价推广 2 + 结论 1 + 灵活 1
        w = [1 + 0.15 * i for i in range(q)]
        alloc = [round(core * x / sum(w)) for x in w]
        print(f'\n  按 {q} 个问题、正文 {tgt} 页的预算（后面的问题更深，页数递增）：')
        print('    摘要 2 · 问题重述与分析 4 · 假设与符号 2 · ' +
              ' · '.join(f'问题{i + 1} {a}' for i, a in enumerate(alloc)) + ' · 模型评价与推广 2 · 结论 1')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
