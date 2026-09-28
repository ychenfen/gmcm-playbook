# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""局部搜索第二版：多核数、多场景、多起点，从 runs/pf 里的组合最优方案出发。

与 ls_driver.py 的区别：
- 起点从 runs/pf/*.json 全量结果里选（覆盖 k=2..5、问题1/2/3、keff 变体），不再只看 k=4
- 同一 (用例, k, 问题) 可跑多个种子，结果按 seed 分文件，断点续跑
- 起点重建时尊重 keff（少用核的方案补空核）
"""
import json, os, sys, glob, argparse, collections, time
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep2 import make_plan, pad
from localsearch import search

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def job(args):
    case, k, problem, algo, div, keff, budget, rundir, seed = args
    out = os.path.join(rundir, f'{case}_k{k}_p{problem}_s{seed}.json')
    if os.path.exists(out):
        return ('skip', case)
    g = json.load(open(os.path.join(ROOT, 'pkg', 'data', case + '.json')))
    plan0 = pad(make_plan(g, keff or k, algo, div), k)
    t0 = time.time()
    try:
        best, bestplan, tries = search(case, plan0, problem, budget_sec=budget, seed=seed)
    except Exception as exc:
        best, bestplan, tries = None, None, 0
        err = f'{type(exc).__name__}: {exc}'
    rec = {'case': case, 'k': k, 'problem': problem, 'seed': seed,
           'start': [algo, div, keff], 'makespan': best, 'tries': tries,
           'secs': round(time.time() - t0, 1)}
    if best is None:
        rec['err'] = locals().get('err', 'evaluate failed')
    if bestplan:
        pj = os.path.join(rundir, 'plans', f'{case}_k{k}_p{problem}_s{seed}.json')
        os.makedirs(os.path.dirname(pj), exist_ok=True)
        json.dump(bestplan, open(pj, 'w'))
    tmp = out + '.tmp'
    json.dump(rec, open(tmp, 'w'))
    os.replace(tmp, out)
    return ('done', case)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', nargs='+', default=['all'])
    ap.add_argument('--cores', nargs='+', type=int, default=[2, 3, 4, 5])
    ap.add_argument('--problems', nargs='+', type=int, default=[1, 2])
    ap.add_argument('--seeds', nargs='+', type=int, default=[1])
    ap.add_argument('--budget', type=float, default=600.0)
    ap.add_argument('--rundir', default='runs/ls2')
    ap.add_argument('-j', type=int, default=24)
    a = ap.parse_args()
    rundir = os.path.join(ROOT, a.rundir)
    os.makedirs(rundir, exist_ok=True)

    best = {}
    for f in glob.glob(os.path.join(ROOT, 'runs', 'pf', '*.json')):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if 'err' in r or r.get('makespan') is None:
            continue
        key = (r['case'], r['k'], r['problem'])
        if key not in best or r['makespan'] < best[key][3]:
            best[key] = (r['algo'], r['div'], r.get('keff'), r['makespan'])

    cases = a.cases
    if cases == ['all']:
        cases = sorted({k[0] for k in best})
    jobs = []
    for c in cases:
        for k in a.cores:
            for p in a.problems:
                if (c, k, p) not in best:
                    continue
                algo, div, keff, _ = best[(c, k, p)]
                for s in a.seeds:
                    jobs.append((c, k, p, algo, div, keff, a.budget, rundir, s))
    print(f'局部搜索作业 {len(jobs)} 个，每个 {a.budget:.0f}s，并行 {a.j}，'
          f'理论墙钟 {len(jobs)*a.budget/a.j/3600:.1f} 小时', flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=a.j) as ex:
        for f in as_completed([ex.submit(job, j) for j in jobs]):
            done += 1
            if done % 20 == 0:
                print(f'  进度 {done}/{len(jobs)}  {time.strftime("%H:%M:%S")}', flush=True)
    print('局部搜索完成', flush=True)
