# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方公布为准）
"""把 paper/numbers.json 转成 LaTeX 宏 paper/tex/numbers.tex，正文用 \\V{键名} 引用。

格式规则（按键名）：加速比 2 位小数；问题3 缓存比值 3 位；达成率、命中率、改进率写成百分数；
字节量已是 MB，1 位小数；计数取整。任何正文数字都应经由本文件进入论文，禁止手抄。
"""
import json, os, re

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def fmt(key, v):
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, str):
        return v.replace('_', '\\_')
    if key.startswith('figx_'):
        if key.endswith('_pct'):
            return f'{v:.0f}\\%'
        if isinstance(v, int) or re.search(r'_n_|_n$|_zero|_above|_below|pairs', key):
            return f'{int(round(v)):,}'.replace(',', '{,}')
        return f'{v:.2f}'
    if key.startswith('fig_'):
        if re.search(r'_pct|hit|^fig_miss_', key):
            return f'{v:.1f}\\%'
        if re.search(r'ms\d|msA|msB|_n_|pairs', key) or isinstance(v, int):
            return f'{int(round(v)):,}'.replace(',', '{,}')
        return f'{v:.3f}' if re.search(r'p3_|ddr_|sens_', key) else f'{v:.2f}'
    if isinstance(v, float) and re.search(r'^cc_.*_hit$', key):
        return f'{v * 100:.1f}\\%'
    if isinstance(v, float) and re.search(r'_pct$', key) and not key.startswith('fig_'):
        return f'{v:.1f}\\%'
    if isinstance(v, float) and re.search(r'_sp$|_best$|_same$', key):
        return f'{v:.3f}' if key.startswith('cc_') else f'{v:.2f}'
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer() and not re.search(r'mean|max|min|ratio|speedup', key)):
        return f'{int(v):,}'.replace(',', '{,}')
    if not isinstance(v, float):
        return None
    if re.search(r'achieve|_eff_', key):
        return f'{v * 100:.0f}\\%'
    if re.search(r'hit_(mean|max)', key):
        return f'{v * 100:.1f}\\%'
    if key.endswith('_pct'):
        return f'{v:.1f}\\%'
    if key.endswith('_MB') or '_MB_' in key:
        return f'{v:.1f}'
    if key.startswith('p3_') and re.search(r'best|same', key):
        return f'{v:.3f}'
    if re.search(r'^ls_.*(tries|secs)', key):
        return f'{v:.0f}'
    if 'nsg' in key or 'median' in key and 'nsg' in key:
        return f'{v:.0f}'
    if key.startswith('added_ratio') or key.startswith('pA_over'):
        return f'{v:.2f}'
    return f'{v:.2f}'


def main():
    N = json.load(open(os.path.join(ROOT, 'paper', 'numbers.json'), encoding='utf-8'))
    lines = ['% 由 src/numbers_tex.py 自动生成，勿手改。来源：paper/numbers.json',
             '\\makeatletter',
             '\\newcommand{\\V}[1]{\\@ifundefined{v@#1}{\\textbf{??\\detokenize{#1}??}}{\\csname v@#1\\endcsname}}']
    n = 0
    fn = os.path.join(ROOT, 'paper', 'fig', 'fig_numbers.json')        # 图注中的数字（make_figures.py 生成）
    if os.path.exists(fn):
        for k, v in json.load(open(fn, encoding='utf-8')).items():
            N['fig_' + k] = v
    fx = os.path.join(ROOT, 'paper', 'fig', 'fig_numbers_extra.json')  # 模型检验补充图（extra_figures.py 生成）
    if os.path.exists(fx):
        for k, v in json.load(open(fx, encoding='utf-8')).items():
            N['figx_' + k] = v
    ff = os.path.join(ROOT, 'paper', 'fig', 'fig_numbers_fast.json')   # 快速模式质量（fast_mode.py 生成）
    if os.path.exists(ff):
        for k, v in json.load(open(ff, encoding='utf-8')).items():
            N['figx_fast_' + k] = v

    def flat(prefix, v):
        if isinstance(v, dict):
            for kk, vv in v.items():
                yield from flat(f'{prefix}_{kk}', vv)
        elif isinstance(v, list):
            for i, vv in enumerate(v):
                yield from flat(f'{prefix}_{i}', vv)
        else:
            yield prefix, v
    for k0, v0 in sorted(N.items()):
        for k, v in flat(k0, v0):
            s = fmt(k, v)
            if s is not None:
                lines.append(f'\\expandafter\\def\\csname v@{k}\\endcsname{{{s}}}'); n += 1
    lines.append('\\makeatother')
    out = os.path.join(ROOT, 'paper', 'tex', 'numbers.tex')
    open(out, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('写出', out, n, '个宏')


if __name__ == '__main__':
    main()
