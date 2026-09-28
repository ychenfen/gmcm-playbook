# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方公布为准）
"""三种构造算法生成方案的耗时（不含官方评估），4 核，每个用例每种算法取一组代表参数，单进程顺序执行。
输出 runs/time_algos.json：每条含用例、算法、操作数、秒数。机器负载高时测得的是上限。"""
import json, os, sys, time, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep2 import make_plan
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
out = []
for gp in sorted(glob.glob(os.path.join(ROOT, 'pkg/data/case_[0-9][0-9][0-9].json'))):
    g = json.load(open(gp)); n = sum(1 for o in g['ops'] if o['op'] not in ('COPY_IN', 'COPY_OUT'))
    for algo, div in (('lpt', 0.25), ('band', 256), ('phase', 50000)):
        t0 = time.perf_counter(); make_plan(g, 4, algo, div); dt = time.perf_counter() - t0
        out.append({'case': os.path.basename(gp)[:-5], 'algo': algo, 'n_ops': n, 'secs': dt})
json.dump(out, open(os.path.join(ROOT, 'runs', 'time_algos.json'), 'w'), indent=1)
print('done', len(out))
