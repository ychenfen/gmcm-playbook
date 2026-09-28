# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具名称：Claude Code；版本/型号：Claude Opus 5.5；开发机构：Anthropic；版本颁布日期：2026 年 9 月 22 日
# 快速模式的求解质量：只用 solve.py 的 9 组代表参数（不做后处理）时的逐用例最优，
# 数据直接取自扫描阶段的官方评估记录 runs/pf/，不重新评估。输出 paper/fig/fig_numbers_fast.json。
import csv, glob, json, os, statistics as st

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
FAST = {('lpt', 0.25), ('lpt', 1.0), ('lpt', 4.0), ('band', 16.0), ('band', 256.0), ('band', 4096.0),
        ('phase', 2000.0), ('phase', 10000.0), ('phase', 50000.0)}

single = {}
for r in csv.DictReader(open(os.path.join(ROOT, 'deliverables', 'appendix_p1.csv'), encoding='utf-8')):
    single[r['case']] = int(r['singlecore_makespan'])

best = {}
for f in glob.glob(os.path.join(ROOT, 'runs', 'pf', '*.json')):
    try:
        r = json.load(open(f))
    except Exception:
        continue
    if not r.get('makespan') or 'err' in r or r.get('keff', r['k']) != r['k']:
        continue
    if (r['algo'], float(r['div'])) not in FAST:
        continue
    key = (r['problem'], r['k'], r['case'])
    best[key] = min(best.get(key, 1 << 62), r['makespan'])

out = {}
for p, ks in ((1, (2, 3, 4, 5)), (2, (2, 3, 4, 5)), (3, (1, 2, 3, 4, 5))):
    for k in ks:
        sp = [single[c] / best[(p, k, c)] for c in single if (p, k, c) in best]
        out[f'p{p}_k{k}_n'] = len(sp)
        if sp:
            out[f'p{p}_k{k}_mean'] = st.mean(sp)
# 最大用例快速求解的实测用时（solve.py -j 8，/usr/bin/time -p 记录于 runs/fast_timing_case014_p2_k4.log）
import re
tl = os.path.join(ROOT, 'runs', 'fast_timing_case014_p2_k4.log')
if os.path.exists(tl):
    t = open(tl, encoding='utf-8').read()
    out['big_wall_s'] = float(re.search(r'^real ([\d.]+)', t, re.M).group(1))
    out['big_cpu_min'] = (float(re.search(r'^user ([\d.]+)', t, re.M).group(1)) + float(re.search(r'^sys ([\d.]+)', t, re.M).group(1))) / 60
json.dump(out, open(os.path.join(ROOT, 'paper', 'fig', 'fig_numbers_fast.json'), 'w'), indent=1)
print(json.dumps(out, indent=1))
