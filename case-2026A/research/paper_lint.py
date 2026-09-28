# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""论文质量检查（去 AI 味 + 2025 A 题优秀论文暴露过的毛病）。

用法:  python3 src/paper_lint.py paper/main.tex [paper/sec_*.tex ...]
       python3 src/paper_lint.py --selftest

检查项（每项都对应一个真实出现过的问题，见 paper/lessons_from_2025A.md）：
  A 词句   禁用词（用户 CLAUDE.md + 2025 论文高频虚词）、"显著/有效"后面没跟数字、首先/其次/最后排比
  B 节奏   同一段内句长过于均匀（AI 文本的典型特征）
  C 格式   列表项、加粗密度过高（论文正文应以段落为主）
  D 论断   "最优/接近最优/下界"类声明没有引用下界表或具体数值（P2、P4 的无证据最优性声明）
  E 数字   正文数字必须能在 deliverables/ 或 paper/facts.json 里找到出处（P3 的代码与正文对不上）
  F 常见笔误  领域搜索→邻域搜索、NAGA-II→NSGA-II 等 2025 论文里真实出现过的错
  G 合规   参考文献里不得出现 AI 工具；全文须有 AI 使用披露段

只提示、不改写。数字检查是硬门槛：出处不明的数字不许进终稿。
"""
import re, sys, os, json, glob, csv, statistics

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

BANNED = ["值得注意的是", "综上所述", "不难发现", "由此可见", "基于以上分析", "具有重要意义",
          "日益增长的", "具有广泛的应用前景", "提供了新思路", "提供了新视角", "奠定了坚实", "让我们",
          "深入探讨", "突破性", "首创", "卓越", "创新性地", "充分证明", "有机统一", "不言而喻",
          "至关重要", "毋庸置疑", "显而易见"]
VAGUE = ["显著", "有效", "大幅", "明显"]              # 同一句里必须有数字
WATCH = ["协同", "智能", "深入", "全面", "赋能"]
TYPOS = {"领域搜索": "邻域搜索", "NAGA-II": "NSGA-II", "NAGA-Ⅱ": "NSGA-II", "面效": "（疑似笔误）",
         "模拟推火": "模拟退火", "禁忌收索": "禁忌搜索", "帕累托前延": "帕累托前沿"}
OPTIMAL = re.compile(r"(接近|达到|逼近)?(理论)?(最优|下界|上界|最优解|近似最优)")
BOUND_REF = re.compile(r"(下界|上界|达成率|gap|\\ref\{tab:bound|\\ref\{fig:bound|[0-9]+(\.[0-9]+)?\s*(%|倍))")
AI_NAMES = re.compile(r"(DeepSeek|ChatGPT|GPT-?\d|Claude|文心|通义|Kimi|豆包|Gemini|Copilot)", re.I)
WHITELIST = {1000, 2024, 2025, 2026, 1024, 2048, 4096, 8192, 131072, 524288, 1048576}


def strip_tex(t):
    t = re.sub(r'(?<!\\)%.*', '', t)
    t = re.sub(r'\\begin\{(lstlisting|verbatim|minted|equation\*?|align\*?|gather\*?)\}.*?\\end\{\1\}',
               ' ', t, flags=re.S)
    t = re.sub(r'\$\$.*?\$\$|\\\[.*?\\\]', ' ', t, flags=re.S)
    t = re.sub(r'\$[^$]*\$', ' ', t)
    t = re.sub(r'\\(label|ref|eqref|cite|includegraphics|input|url|href)(\[[^\]]*\])?\{[^}]*\}', ' ', t)
    return t


def known_numbers():
    """deliverables/ 与 paper/facts.json 里的所有数值，按多种显示精度展开。"""
    vals = set()
    def add(x):
        try:
            f = float(str(x).replace(',', ''))
        except Exception:
            return
        vals.add(round(f)); vals.add(round(f, 1)); vals.add(round(f, 2)); vals.add(round(f, 3))
        vals.add(round(f * 100, 1)); vals.add(round(f * 100))          # 比例写成百分数
    for f in glob.glob(os.path.join(ROOT, 'deliverables', '*.csv')):
        for row in csv.reader(open(f)):
            for x in row:
                add(x)
    def walk(o):
        if isinstance(o, dict):
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
        else:
            add(o)
    sj = os.path.join(ROOT, 'deliverables', 'summary.json')
    if os.path.exists(sj):
        walk(json.load(open(sj)))
    fj = os.path.join(ROOT, 'paper', 'facts.json')
    if os.path.exists(fj):
        for k in json.load(open(fj)):
            add(k)
    return vals


def sentences(par):
    return [s for s in re.split(r'[。！？；]', par) if len(re.findall(r'[\u4e00-\u9fff]', s)) >= 4]


def lint_text(raw, name, known):
    t = strip_tex(raw)
    lines = t.split('\n')
    han = len(re.findall(r'[\u4e00-\u9fff]', t)) or 1
    issues = []
    def hit(cat, msg, ln=None):
        issues.append((cat, ln, msg))

    for i, l in enumerate(lines, 1):
        for w in BANNED:
            if w in l: hit('A 词句', f'禁用词「{w}」', i)
        for w, fix in TYPOS.items():
            if w in l: hit('F 笔误', f'「{w}」→ {fix}', i)
        for s in re.split(r'[。！？；]', l):
            for w in VAGUE:
                if w in s and not re.search(r'\d', s):
                    hit('A 词句', f'「{w}」同句没有数字支撑：{s.strip()[:40]}', i)
            if OPTIMAL.search(s) and not BOUND_REF.search(s) and '目标' not in s and '最优化' not in s:
                hit('D 论断', f'最优性/下界表述没有引证据：{s.strip()[:40]}', i)
        # 数字出处
        for m in re.finditer(r'(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+\.\d+|\d{4,})(?![\w.])', l):
            s = m.group(1)
            v = float(s.replace(',', ''))
            if v in WHITELIST or (1900 <= v <= 2100 and '.' not in s):
                continue
            prec = len(s.split('.')[1]) if '.' in s else 0
            if round(v, prec) not in known and round(v) not in known:
                hit('E 数字', f'数字 {s} 在 deliverables/ 与 facts.json 中都找不到出处', i)
        if re.search(r'首先.*其次.*最后', l):
            hit('A 词句', '首先/其次/最后 三段式', i)

    # 段落节奏
    for pi, par in enumerate(re.split(r'\n\s*\n', t)):
        ss = sentences(par)
        if len(ss) >= 4:
            L = [len(re.findall(r'[\u4e00-\u9fff]', s)) for s in ss]
            cv = statistics.pstdev(L) / statistics.mean(L)
            if cv < 0.25:
                hit('B 节奏', f'第 {pi+1} 段 {len(ss)} 句长度过于均匀（变异系数 {cv:.2f}，建议 >0.35）：{ss[0].strip()[:24]}…')
    # 格式密度
    items, bolds = raw.count('\\item'), raw.count('\\textbf') + raw.count('**')
    if items / han * 1000 > 6:
        hit('C 格式', f'列表项 {items} 个，{items/han*1000:.1f}/千字（建议 ≤6），正文尽量写成段落')
    if bolds / han * 1000 > 3:
        hit('C 格式', f'加粗 {bolds} 处，{bolds/han*1000:.1f}/千字（建议 ≤3）')
    # 合规
    bib = raw[raw.find('thebibliography'):] if 'thebibliography' in raw else ''
    if bib and AI_NAMES.search(bib):
        hit('G 合规', f'参考文献里出现 AI 工具「{AI_NAMES.search(bib).group(0)}」——AI 输出不能当学术依据')
    watch = sum(t.count(w) for w in WATCH + VAGUE + BANNED)
    return issues, han, watch / han * 1e4


def main(paths, require_disclosure=True):
    known = known_numbers()
    alltext, bad = '', 0
    for p in paths:
        raw = open(p, encoding='utf-8').read()
        alltext += raw
        issues, han, dens = lint_text(raw, p, known)
        print(f'\n== {p}  汉字 {han}  虚词密度 {dens:.1f}/万字（2025 优秀论文最低 16.9）')
        for cat, ln, msg in sorted(issues, key=lambda x: (x[0], x[1] or 0)):
            print(f'  [{cat}] ' + (f'L{ln}: ' if ln else '') + msg)
        bad += sum(1 for c, _, _ in issues if c[0] in 'DEG')
        if not issues:
            print('  无问题')
    if require_disclosure and paths and not re.search(r'AI\s*(工具)?(使用)?(披露|说明|声明)|人工智能工具使用', alltext):
        print('\n[G 合规] 全文没有找到 AI 使用披露段（规定要求在论文末尾披露，未披露取消资格）')
        bad += 1
    print(f'\n硬门槛问题（D 论断 / E 数字 / G 合规）: {bad} 个' + ('，终稿前必须清零' if bad else ''))
    return bad


SAMPLE = r"""
\section{问题一}
值得注意的是，本文首创的算法取得了显著提升，充分证明了其卓越性能。
首先，我们构建模型；其次，我们求解模型；最后，我们分析结果。
该算法在 Conv_Case0 上已经接近理论最优值。
4 核平均加速比为 2.53，理想调度上界为 4.62，达成率 55%。
采用基于领域搜索的贪心算法，并与 NAGA-II 对比，额外搬运量为 123457。

我们选择了这个方法。我们实现了这个方法。我们测试了这个方法。我们记录了这个结果。

\begin{thebibliography}{9}\bibitem{a} DeepSeek. DeepSeek-R1, 2025.\end{thebibliography}
"""

if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        tmp = '/tmp/_paper_lint_sample.tex'
        open(tmp, 'w').write(SAMPLE)
        bad = main([tmp])
        sys.exit(0 if bad >= 4 else 1)
    sys.exit(1 if main(sys.argv[1:]) else 0)
