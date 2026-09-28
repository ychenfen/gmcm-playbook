# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方公布为准）
"""由 deliverables/appendix_p{1,2,3}.csv 生成论文附录长表 paper/tex/tables/app_p{1,2,3}.tex。数字不经手抄。"""
import csv, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
D = os.path.join(ROOT, 'deliverables')
OUT = os.path.join(ROOT, 'paper', 'tex', 'tables')


def n(x):
    return f'{int(x):,}'.replace(',', '{,}')


def p12(p):
    rows = list(csv.DictReader(open(os.path.join(D, f'appendix_p{p}.csv'), encoding='utf-8')))
    head = ('\\begin{footnotesize}\n\\setlength{\\tabcolsep}{2.6pt}\n'
            '\\begin{longtable}{l r rr rr rr rr}\n'
            f'\\caption{{问题{"一二"[p - 1]}逐用例结果：Makespan（周期）与总额外搬运量（字节）}}\\label{{tab:app-p{p}}}\\\\\n'
            '\\toprule\n'
            '\\multirow{2}{*}{用例} & \\multirow{2}{*}{单核基准} & \\multicolumn{2}{c}{2 核} & \\multicolumn{2}{c}{3 核} '
            '& \\multicolumn{2}{c}{4 核} & \\multicolumn{2}{c}{5 核} \\\\\n'
            '\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}\\cmidrule(lr){7-8}\\cmidrule(lr){9-10}\n'
            ' & & Makespan & 额外搬运 & Makespan & 额外搬运 & Makespan & 额外搬运 & Makespan & 额外搬运 \\\\\n'
            '\\midrule\n\\endfirsthead\n'
            '\\toprule\n用例 & 单核基准 & \\multicolumn{2}{c}{2 核} & \\multicolumn{2}{c}{3 核} & \\multicolumn{2}{c}{4 核} '
            '& \\multicolumn{2}{c}{5 核} \\\\\n\\midrule\n\\endhead\n\\bottomrule\n\\endfoot\n')
    body = []
    for r in rows:
        cells = [r['case'].replace('_', '\\_'), n(r['singlecore_makespan'])]
        for k in (2, 3, 4, 5):
            cells += [n(r[f'makespan_k{k}']), n(r[f'added_bytes_k{k}'])]
        body.append(' & '.join(cells) + ' \\\\')
    open(os.path.join(OUT, f'app_p{p}.tex'), 'w', encoding='utf-8').write(
        head + '\n'.join(body) + '\n\\end{longtable}\n\\end{footnotesize}\n')


def p3():
    rows = list(csv.DictReader(open(os.path.join(D, 'appendix_p3.csv'), encoding='utf-8')))
    rows.sort(key=lambda r: (r['case'], int(r['k'])))
    head = ('\\begin{footnotesize}\n\\setlength{\\tabcolsep}{3.2pt}\n'
            '\\begin{longtable}{l c rr c rr c}\n'
            '\\caption{问题三逐用例结果：无 L2 与只读 Cache 两种配置的 Makespan（周期）、总额外搬运量（字节）与 Cache 命中率}'
            '\\label{tab:app-p3}\\\\\n\\toprule\n'
            '用例 & 核数 & 无 L2 Makespan & Cache Makespan & 加速比 & 无 L2 额外搬运 & Cache 额外搬运 & 命中率 \\\\\n'
            '\\midrule\n\\endfirsthead\n\\toprule\n'
            '用例 & 核数 & 无 L2 Makespan & Cache Makespan & 加速比 & 无 L2 额外搬运 & Cache 额外搬运 & 命中率 \\\\\n'
            '\\midrule\n\\endhead\n\\bottomrule\n\\endfoot\n')
    body = []
    for r in rows:
        body.append(' & '.join([r['case'].replace('_', '\\_') if r['k'] == '1' else '', r['k'], n(r['noL2_makespan']),
                                n(r['cache_makespan']), f"{float(r['cache_speedup_best']):.4f}",
                                n(r['noL2_added_bytes']), n(r['cache_added_bytes']),
                                f"{float(r['cache_hit_rate']) * 100:.1f}\\%"]) + ' \\\\')
        if r['k'] == '5':
            body.append('\\addlinespace[2pt]')
    open(os.path.join(OUT, 'app_p3.tex'), 'w', encoding='utf-8').write(
        head + '\n'.join(body) + '\n\\end{longtable}\n\\end{footnotesize}\n')


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    p12(1); p12(2); p3()
    print('写出', os.listdir(OUT))
