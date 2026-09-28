# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""对 (case, 核数, 参数) 组合生成方案并调用官方评估器，收集 makespan。"""
import json, os, sys, subprocess, tempfile, argparse
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from algos import build_plan_lpt
from algos2 import build_plan_band
from algos3 import build_plan_listsched

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PY = sys.executable
CFG = os.path.join(ROOT, 'pkg', 'data', 'config.txt')


def one(job):
    try:
        return _one(job)
    except Exception as exc:
        return {'case': job[0], 'k': job[1], 'div': job[2], 'algo': job[4],
                'problem': job[3], 'err': f'{type(exc).__name__}: {exc}'}


def _one(job):
    case, k, div, problem, algo = job
    gpath = os.path.join(ROOT, 'pkg', 'data', case + '.json')
    g = json.load(open(gpath))
    if algo == 'lpt':
        plan = build_plan_lpt(g, k, chunk_div=div)
    elif algo == 'band':
        plan = build_plan_band(g, k, n_bands=int(div))
    else:
        plan = build_plan_listsched(g, k, comm_weight=div)
    nsg = len(set(plan['node_to_subgraph'].values()))
    with tempfile.TemporaryDirectory() as td:
        pp = os.path.join(td, 'plan.json')
        json.dump(plan, open(pp, 'w'))
        ev = os.path.join(ROOT, 'pkg', 'code', f'multicore_cut_evaluate_problem_{problem}.py')
        r = subprocess.run(
            [PY, ev, gpath, pp, '--config', CFG, '-o', os.path.join(td, 'r.json'),
             '--trace-output', os.path.join(td, 't.json'),
             '--log-output', os.path.join(td, 'l.txt')],
            capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            return {'case': case, 'k': k, 'div': div, 'algo': algo, 'problem': problem,
                    'err': (r.stderr or r.stdout)[-300:]}
        res = json.load(open(os.path.join(td, 'r.json')))
    dm = res.get('data_movement_bytes', {})
    return {'case': case, 'k': k, 'div': div, 'algo': algo, 'problem': problem, 'n_subgraphs': nsg,
            'makespan': res['makespan'],
            'orig_bytes': dm.get('original_graph_copy_bytes'),
            'sched_bytes': dm.get('scheduled_copy_bytes'),
            'added_bytes': dm.get('added_copy_bytes'),
            'spill_bytes': dm.get('spill_added_copy_bytes'),
            'n_task_deps': len(res.get('task_dependencies', []))}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', nargs='+', default=['all'])
    ap.add_argument('--cores', nargs='+', type=int, default=[4])
    ap.add_argument('--divs', nargs='+', type=float, default=[2.0])
    ap.add_argument('--problem', type=int, default=1)
    ap.add_argument('--out', required=True)
    ap.add_argument('-j', type=int, default=11)
    ap.add_argument('--algo', default='lpt')
    a = ap.parse_args()
    import glob
    cases = a.cases
    if cases == ['all']:
        cases = sorted(os.path.basename(p)[:-5]
                       for p in glob.glob(os.path.join(ROOT, 'pkg', 'data', 'case_[0-9][0-9][0-9].json')))
    jobs = [(c, k, d, a.problem, a.algo) for c in cases for k in a.cores for d in a.divs]
    with ProcessPoolExecutor(max_workers=a.j) as ex:
        rows = list(ex.map(one, jobs))
    json.dump(rows, open(a.out, 'w'), indent=1)
    errs = [r for r in rows if 'err' in r]
    print(f'完成 {len(rows)} 个作业，失败 {len(errs)}')
    for e in errs[:5]: print('  ERR', e['case'], e['k'], e['div'], e['err'][:150])
