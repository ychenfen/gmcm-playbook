# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""在给定用例上比较：各基础方案 vs 错开读取后处理，问题3评估器下的最优 makespan。"""
import json, os, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep2 import make_plan, pad
from stagger import stagger
from localsearch import evaluate
from finalize import ROOT

CONFIGS = [('lpt', .25), ('lpt', 1), ('lpt', 4), ('band', 16), ('band', 256), ('band', 4096),
           ('phase', 2000), ('phase', 10000), ('phase', 50000)]


def one(args):
    case, k, algo, div = args
    g = json.load(open(os.path.join(ROOT, 'pkg/data', case + '.json')))
    base = pad(make_plan(g, k, algo, div), k)
    gp = os.path.join(ROOT, 'pkg/data', case + '.json')
    with tempfile.TemporaryDirectory() as td:
        m0 = evaluate(gp, base, 3, td)
        try:
            m1 = evaluate(gp, stagger(g, base), 3, td)
        except Exception as e:
            m1 = None
    return case, k, algo, div, m0, m1


if __name__ == '__main__':
    k = int(sys.argv[1]); cases = sys.argv[2:]
    jobs = [(c, k, a, d) for c in cases for a, d in CONFIGS]
    with ProcessPoolExecutor(10) as ex:
        res = list(ex.map(one, jobs))
    import collections
    by = collections.defaultdict(list)
    for r in res:
        by[r[0]].append(r)
    tot0 = tot1 = 0
    for c in cases:
        rows = by[c]
        b0 = min((r for r in rows if r[4]), key=lambda r: r[4])
        b1 = min((r for r in rows if r[5]), key=lambda r: r[5])
        improved = sum(1 for r in rows if r[4] and r[5] and r[5] < r[4] * 0.995)
        worse = sum(1 for r in rows if r[4] and r[5] and r[5] > r[4] * 1.005)
        print(f"{c} k{k}: 不错开最优 {b0[4]:>10,} [{b0[2]}{b0[3]:g}]  错开后最优 {b1[5]:>10,} [{b1[2]}{b1[3]:g}]"
              f"  → {b0[4]/b1[5]:.3f}x   (9 个方案中改善 {improved}，变差 {worse})")
