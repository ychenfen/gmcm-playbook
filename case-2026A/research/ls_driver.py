# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""并行局部搜索驱动：对每个用例取组合最优方案为起点，跑爬山改进。

起点方案由 (algo, div) 确定性重建，无需落盘保存。结果逐用例原子落盘，可断点续跑。
"""
import json, os, sys, glob, argparse, collections, time
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from algos import build_plan_lpt
from algos2 import build_plan_band
from localsearch import search, evaluate

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def make(g, k, algo, div):
    return build_plan_lpt(g, k, div) if algo == 'lpt' else build_plan_band(g, k, int(div))


def job(args):
    case, k, problem, algo, div, budget, rundir, seed = args
    out = os.path.join(rundir, f'{case}_k{k}_p{problem}.json')
    if os.path.exists(out):
        return ('skip', case, problem, None)
    g = json.load(open(os.path.join(ROOT, 'pkg', 'data', case + '.json')))
    plan0 = make(g, k, algo, div)
    t0 = time.time()
    try:
        best, bestplan, tries = search(case, plan0, problem, budget_sec=budget, seed=seed)
    except Exception as exc:
        rec = {'case': case, 'k': k, 'problem': problem, 'err': f'{type(exc).__name__}: {exc}'}
        json.dump(rec, open(out, 'w'))
        return ('err', case, problem, str(exc)[:120])
    rec = {'case': case, 'k': k, 'problem': problem, 'start_algo': algo, 'start_div': div,
           'makespan': best, 'tries': tries, 'secs': round(time.time() - t0, 1),
           'n_subgraphs': len(set(bestplan['node_to_subgraph'].values())) if bestplan else None}
    tmp = out + '.tmp'
    json.dump(rec, open(tmp, 'w'))
    os.replace(tmp, out)
    # 方案本身也存下来，后面出附录表和复现要用
    if bestplan:
        pj = os.path.join(rundir, 'plans', f'{case}_k{k}_p{problem}_plan.json')
        os.makedirs(os.path.dirname(pj), exist_ok=True)
        json.dump(bestplan, open(pj, 'w'))
    return ('done', case, problem, best)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', nargs='+', required=True)
    ap.add_argument('--k', type=int, default=4)
    ap.add_argument('--problems', nargs='+', type=int, default=[1, 2])
    ap.add_argument('--budget', type=float, default=180.0)
    ap.add_argument('--rundir', required=True)
    ap.add_argument('-j', type=int, default=10)
    ap.add_argument('--seed', type=int, default=1)
    a = ap.parse_args()
    rundir = os.path.join(ROOT, a.rundir)
    os.makedirs(rundir, exist_ok=True)

    # 从组合扫描里取每个 (用例,场景) 的最优起点
    pf = json.load(open(os.path.join(ROOT, 'runs', 'pf_k4.json')))
    best = collections.defaultdict(lambda: (None, None, float('inf')))
    for r in pf:
        if 'err' in r or r['k'] != a.k:
            continue
        key = (r['case'], r['problem'])
        if r['makespan'] < best[key][2]:
            best[key] = (r['algo'], r['div'], r['makespan'])

    jobs = []
    for c in a.cases:
        for p in a.problems:
            algo, div, _ = best[(c, p)]
            if algo is None:
                continue
            jobs.append((c, a.k, p, algo, div, a.budget, rundir, a.seed))
    print(f'作业 {len(jobs)} 个，每个预算 {a.budget}s，并行 {a.j}', flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=a.j) as ex:
        for f in as_completed([ex.submit(job, j) for j in jobs]):
            st, c, p, v = f.result()
            done += 1
            if st == 'err':
                print(f'  ERR {c} p{p}: {v}', flush=True)
            if done % 10 == 0:
                print(f'  进度 {done}/{len(jobs)}', flush=True)
    print('完成', flush=True)
