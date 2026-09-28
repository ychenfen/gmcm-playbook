# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方公布为准）
"""论文文本检查（去 AI 味 + 2025 年优秀论文里真实出现过的毛病）。只提示，不改写。

用法:
  python3 paper_lint.py 论文.tex [其他章节.tex ...]      支持 .tex / .md / .txt / .docx
  python3 paper_lint.py 论文.docx --numbers results/ 汇总.csv facts.json
  python3 paper_lint.py --selftest

检查项:
  A 词句   套话、没有数字支撑的程度词、首先/其次/最后
  B 节奏   同一段内句子长度过于均匀
  C 格式   列表、加粗过多
  D 论断   说「最优/接近最优/下界」却没有给数值或差距
  E 数字   （可选，给了 --numbers 才查）正文数字在结果文件里找不到
  F 笔误   2025 年论文里真实出现过的错字
  G 合规   参考文献里的 AI 工具没写全版本/公司/日期；全文没有 AI 使用说明

D、G 两类（以及启用时的 E 类）是硬门槛，终稿前应清零。
"""
import re, sys, os, json, glob, csv, statistics, zipfile

BANNED = ["值得注意的是", "综上所述", "不难发现", "由此可见", "基于以上分析", "具有重要意义",
          "日益增长的", "具有广泛的应用前景", "提供了新思路", "提供了新视角", "奠定了坚实", "让我们",
          "深入探讨", "突破性", "首创", "卓越", "创新性地", "充分证明", "有机统一", "不言而喻",
          "至关重要", "毋庸置疑", "显而易见"]
VAGUE = ["显著", "有效", "大幅", "明显"]              # 同一句里应有数字
WATCH = ["协同", "智能", "深入", "全面", "赋能"]
TYPOS = {"领域搜索": "邻域搜索", "NAGA-II": "NSGA-II", "NAGA-Ⅱ": "NSGA-II", "面效": "（疑似笔误）",
         "模拟推火": "模拟退火", "禁忌收索": "禁忌搜索", "帕累托前延": "帕累托前沿", "遗传算发": "遗传算法",
         "粒子群算发": "粒子群算法", "鲁邦": "鲁棒"}
OPTIMAL = re.compile(r"(接近|达到|逼近)?(理论)?(最优解|近似最优|全局最优|最优|下界|上界)")
EVIDENCE = re.compile(r"(下界|上界|达成率|差距|gap|\\ref\{|[0-9]+(\.[0-9]+)?\s*(%|倍))")
AI_NAMES = re.compile(r"(DeepSeek|ChatGPT|GPT-?\d|Claude|文心|通义|千问|Qwen|Kimi|豆包|Gemini|Copilot|智谱|GLM)", re.I)
DISCLOSURE = re.compile(r"(AI|人工智能)\s*(工具)?(辅助)?(使用|应用)?\s*(披露|说明|声明|情况)")
WHITELIST = {1000, 1024, 2048, 4096, 8192}


def read_any(path):
    if path.lower().endswith('.docx'):
        with zipfile.ZipFile(path) as z:
            xml = z.read('word/document.xml').decode('utf-8')
        xml = re.sub(r'</w:p>', '\n\n', xml)
        return re.sub(r'<[^>]+>', '', xml)
    return open(path, encoding='utf-8').read()


def strip_tex(t, is_tex=True):
    if is_tex:
        t = re.sub(r'(?<!\\)%.*', '', t)             # 只有 .tex 里的 % 是注释
    t = re.sub(r'\\begin\{(lstlisting|verbatim|minted|equation\*?|align\*?|gather\*?)\}.*?\\end\{\1\}',
               ' ', t, flags=re.S)
    t = re.sub(r'\$\$.*?\$\$|\\\[.*?\\\]', ' ', t, flags=re.S)
    t = re.sub(r'\$[^$]*\$', ' ', t)
    t = re.sub(r'\\(label|ref|eqref|cite|includegraphics|input|url|href)(\[[^\]]*\])?\{[^}]*\}', ' ', t)
    t = re.sub(r'```.*?```', ' ', t, flags=re.S)                     # Markdown 代码块
    return t


def known_numbers(paths):
    """从结果文件（csv/json/txt，或目录下的这些文件）收集数值，按多种显示精度展开。"""
    vals = set()
    def add(x):
        try:
            f = float(str(x).replace(',', ''))
        except Exception:
            return
        for d in (0, 1, 2, 3, 4):
            vals.add(round(f, d))
        vals.add(round(f * 100, 1)); vals.add(round(f * 100, 2)); vals.add(round(f * 100))
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items(): add(k); walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
        else:
            add(o)
    files = []
    for p in paths:
        if os.path.isdir(p):
            for ext in ('csv', 'json', 'txt'):
                files += glob.glob(os.path.join(p, '**', '*.' + ext), recursive=True)
        else:
            files.append(p)
    for f in files:
        try:
            if f.endswith('.json'):
                walk(json.load(open(f, encoding='utf-8')))
            elif f.endswith('.csv'):
                for row in csv.reader(open(f, encoding='utf-8', errors='ignore')):
                    for x in row: add(x)
            else:
                for x in re.findall(r'-?\d+(?:\.\d+)?', open(f, encoding='utf-8', errors='ignore').read()):
                    add(x)
        except Exception as e:
            print(f'  [提示] 读取 {f} 失败：{e}')
    return vals


def sentences(par):
    return [s for s in re.split(r'[。！？；]', par) if len(re.findall(r'[\u4e00-\u9fff]', s)) >= 4]


def lint_text(raw, known, is_tex=True):
    t = strip_tex(raw, is_tex)
    lines = t.split('\n')
    han = len(re.findall(r'[\u4e00-\u9fff]', t)) or 1
    issues = []
    def hit(cat, msg, ln=None):
        issues.append((cat, ln, msg))

    for i, l in enumerate(lines, 1):
        for w in BANNED:
            if w in l: hit('A 词句', f'套话「{w}」', i)
        for w, fix in TYPOS.items():
            if w in l: hit('F 笔误', f'「{w}」→ {fix}', i)
        for s in re.split(r'[。！？；]', l):
            for w in VAGUE:
                if w in s and not re.search(r'\d', s) and '显著性' not in s:
                    hit('A 词句', f'「{w}」同句没有数字支撑：{s.strip()[:40]}', i)
            if OPTIMAL.search(s) and not EVIDENCE.search(s) and not re.search(r'目标|最优化|求解|模型', s):
                hit('D 论断', f'最优性/下界说法没有给数值或差距：{s.strip()[:40]}', i)
        if known is not None:
            for m in re.finditer(r'(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+\.\d+|\d{4,})(?![\w.])', l):
                s = m.group(1)
                v = float(s.replace(',', ''))
                if v in WHITELIST or (1900 <= v <= 2100 and '.' not in s):
                    continue
                prec = len(s.split('.')[1]) if '.' in s else 0
                if round(v, prec) not in known and round(v) not in known:
                    hit('E 数字', f'数字 {s} 在结果文件里找不到', i)
        if re.search(r'首先.*其次.*最后', l):
            hit('A 词句', '首先/其次/最后 三段式', i)

    for pi, par in enumerate(re.split(r'\n\s*\n', t)):
        ss = sentences(par)
        if len(ss) >= 4:
            L = [len(re.findall(r'[\u4e00-\u9fff]', s)) for s in ss]
            cv = statistics.pstdev(L) / statistics.mean(L)
            if cv < 0.25:
                hit('B 节奏', f'第 {pi+1} 段 {len(ss)} 句长度过于均匀（变异系数 {cv:.2f}，建议 >0.35）：{ss[0].strip()[:24]}…')
    items = raw.count('\\item') + len(re.findall(r'^\s*[-*]\s', raw, flags=re.M))
    bolds = raw.count('\\textbf') + raw.count('**') // 2
    if items / han * 1000 > 6:
        hit('C 格式', f'列表项 {items} 个，{items/han*1000:.1f}/千字（建议 ≤6），正文尽量写成段落')
    if bolds / han * 1000 > 3:
        hit('C 格式', f'加粗 {bolds} 处，{bolds/han*1000:.1f}/千字（建议 ≤3）')

    # 参考文献里的 AI 工具：附件4 第3条允许标注，但须写全名称、版本/型号、开发机构、发布日期
    starts = [m.start() for m in re.finditer(r'\\begin\{thebibliography\}|\n\s*参考文献\s*\n', raw)]
    bib = raw[starts[-1]:] if starts else ''
    for entry in re.split(r'\\bibitem|\n\s*\[\d+\]', bib):
        a = AI_NAMES.search(entry)
        if not a:
            continue
        miss = []
        if not re.search(r'版本|型号|[vV]\d|\d+\.\d+|-[A-Z0-9]', entry): miss.append('版本/型号')
        if not re.search(r'公司|机构|Inc|Anthropic|OpenAI|Google|深度求索|百度|阿里|字节|月之暗面|智谱|Microsoft', entry, re.I):
            miss.append('开发机构')
        if not re.search(r'(19|20)\d\d', entry): miss.append('发布日期')
        if miss:
            hit('G 合规', f'参考文献中的 AI 工具「{a.group(0)}」缺少：{"、".join(miss)}')
        else:
            hit('A 词句', f'参考文献引用了 AI 工具「{a.group(0)}」：规定允许，但这类内容可能不被评阅认可，能换正式文献就换')
    watch = sum(t.count(w) for w in WATCH + VAGUE + BANNED)
    return issues, han, watch / han * 1e4


def main(paths, numbers=None, require_disclosure=True):
    known = known_numbers(numbers) if numbers else None
    alltext, bad = '', 0
    for p in paths:
        raw = read_any(p)
        alltext += raw
        issues, han, dens = lint_text(raw, known, p.lower().endswith('.tex'))
        print(f'\n== {p}  汉字 {han}  虚词密度 {dens:.1f}/万字（2025 A 题优秀论文最低 16.9）')
        for cat, ln, msg in sorted(issues, key=lambda x: (x[0], x[1] or 0)):
            print(f'  [{cat}] ' + (f'L{ln}: ' if ln else '') + msg)
        bad += sum(1 for c, _, _ in issues if c[0] in 'DEG')
        if not issues:
            print('  无问题')
    if require_disclosure and paths and not DISCLOSURE.search(alltext):
        print('\n[G 合规] 全文没找到 AI 使用说明段（用了 AI 就要写：工具名称、版本、公司、发布日期、用在哪些环节）')
        bad += 1
    print(f'\n硬门槛问题（D 论断 / G 合规' + (' / E 数字' if numbers else '') + f'）: {bad} 个'
          + ('，终稿前应清零' if bad else ''))
    return bad


SAMPLE = r"""
\section{问题一}
值得注意的是，本文首创的算法取得了显著提升，充分证明了其卓越性能。
首先，我们构建模型；其次，我们求解模型；最后，我们分析结果。
该算法在用例 1 上已经接近理论最优值。
平均加速比为 2.53，理想上界为 4.62，达成率 55%。
采用基于领域搜索的贪心算法，并与 NAGA-II 对比，额外搬运量为 123457。

我们选择了这个方法。我们实现了这个方法。我们测试了这个方法。我们记录了这个结果。

\begin{thebibliography}{9}\bibitem{a} DeepSeek. DeepSeek-R1.\end{thebibliography}
"""

if __name__ == '__main__':
    args = sys.argv[1:]
    if args == ['--selftest']:
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), '_paper_lint_sample.tex')
        open(tmp, 'w', encoding='utf-8').write(SAMPLE)
        bad = main([tmp], numbers=[])
        print('\n自检', '通过' if bad >= 3 else '失败')
        sys.exit(0 if bad >= 3 else 1)
    if not args:
        print(__doc__); sys.exit(2)
    nums = None
    if '--numbers' in args:
        i = args.index('--numbers')
        nums, args = args[i + 1:], args[:i]
    sys.exit(1 if main(args, nums) else 0)
