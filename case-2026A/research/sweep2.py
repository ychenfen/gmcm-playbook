# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""断点续跑的批量评估器。

每个作业结果单独落盘到 rundir/<case>_k<k>_<algo>_<div>_p<problem>.json；
重启时自动跳过已完成的作业。竞价实例被回收后直接重跑同一条命令即可续上。
"""
import json, os, sys, subprocess, tempfile, argparse, glob, traceback, time
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from algos import build_plan_lpt
from algos2 import build_plan_band
from algos3 import build_plan_listsched
from algos4 import build_plan_phase
from algos5 import build_plan_cluster

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PY = sys.executable
CFG = os.path.join(ROOT, 'pkg', 'data', 'config.txt')


def tag(case, k, algo, div, problem, keff=None):
    d = f'{div:g}'.replace('.', 'p')
    base = f'{case}_k{k}_{algo}_{d}_p{problem}'
    return base if (keff is None or keff == k) else f'{base}_e{keff}'   # keff==k 时文件名不变，续跑兼容


def pad(plan, k):
    """用 keff 个核造的方案补空核到 k 核（小图上少用核反而快：跨核同步延迟是固定成本）。"""
    cs = plan['core_schedules']
    return {'node_to_subgraph': plan['node_to_subgraph'],
            'core_schedules': cs + [[] for _ in range(k - len(cs))]}


def make_plan(g, k, algo, div):
    if algo == 'lpt':
        return build_plan_lpt(g, k, chunk_div=div)
    if algo == 'band':
        return build_plan_band(g, k, n_bands=int(div))
    if algo == 'sched':
        return build_plan_listsched(g, k, comm_weight=div)
    if algo == 'phase':                      # div = sync_penalty
        return build_plan_phase(g, k, comm_weight=1.0, sync_penalty=div)
    if algo == 'phasec':                     # 缓存感知相位（问题3）：div = sync_penalty
        return build_plan_phase(g, k, comm_weight=1.0, sync_penalty=div, cache_bw=250.0)
    if algo == 'cluster':
        return build_plan_cluster(g, k)
    raise ValueError(f'unknown algo {algo}')


def one(job):
    case, k, div, problem, algo, rundir, keff = job
    out = os.path.join(rundir, tag(case, k, algo, div, problem, keff) + '.json')
    if os.path.exists(out):
        return ('skip', out)
    rec = {'case': case, 'k': k, 'div': div, 'algo': algo, 'problem': problem, 'keff': keff}
    try:
        gpath = os.path.join(ROOT, 'pkg', 'data', case + '.json')
        g = json.load(open(gpath))
        plan = pad(make_plan(g, keff, algo, div), k)
        rec['n_subgraphs'] = len(set(plan['node_to_subgraph'].values()))
        with tempfile.TemporaryDirectory() as td:
            pp = os.path.join(td, 'plan.json')
            json.dump(plan, open(pp, 'w'))
            ev = os.path.join(ROOT, 'pkg', 'code',
                              f'multicore_cut_evaluate_problem_{problem}.py')
            r = subprocess.run(
                [PY, ev, gpath, pp, '--config', CFG,
                 '-o', os.path.join(td, 'r.json'),
                 '--trace-output', os.path.join(td, 't.json'),
                 '--log-output', os.path.join(td, 'l.txt')],
                capture_output=True, text=True, timeout=3600)
            if r.returncode != 0:
                rec['err'] = (r.stderr or r.stdout)[-300:]
            else:
                res = json.load(open(os.path.join(td, 'r.json')))
                dm = res.get('data_movement_bytes', {})
                rec.update(makespan=res['makespan'],
                           orig_bytes=dm.get('original_graph_copy_bytes'),
                           sched_bytes=dm.get('scheduled_copy_bytes'),
                           added_bytes=dm.get('added_copy_bytes'),
                           spill_bytes=dm.get('spill_added_copy_bytes'),
                           cache={k: res.get('cache_stats', {}).get(k)
                                  for k in ('hit_rate', 'hits', 'accesses', 'hit_bytes', 'miss_bytes')}
                                 if 'cache_stats' in res else None,
                           n_task_deps=len(res.get('task_dependencies', [])))
    except Exception as exc:
        rec['err'] = f'{type(exc).__name__}: {exc}\n{traceback.format_exc()[-400:]}'
    tmp = out + '.tmp'
    json.dump(rec, open(tmp, 'w'))
    os.replace(tmp, out)          # 原子写，回收时不会留半截文件
    return ('done', out)


def assemble(rundir, outfile):
    rows = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(rundir, '*.json')))
            if not f.endswith('.tmp')]
    tmp = f'{outfile}.{os.getpid()}.tmp'
    json.dump(rows, open(tmp, 'w'), indent=1)
    os.replace(tmp, outfile)          # 原子替换：多个扫描并发汇总时不会写坏
    return rows


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', nargs='+', default=['all'])
    ap.add_argument('--cores', nargs='+', type=int, default=[4])
    ap.add_argument('--divs', nargs='+', type=float, default=[2.0])
    ap.add_argument('--algo', default='lpt')
    ap.add_argument('--problem', nargs='+', type=int, default=[1])
    ap.add_argument('--rundir', required=True)
    ap.add_argument('--out')
    ap.add_argument('-j', type=int, default=10)
    ap.add_argument('--assemble-only', action='store_true')
    ap.add_argument('--keffs', nargs='+', type=int, default=None,
                    help='只用其中 keff 个核（<k 才生效）；不给则 keff=k')
    a = ap.parse_args()

    rundir = os.path.join(ROOT, a.rundir)
    os.makedirs(rundir, exist_ok=True)
    outfile = os.path.join(ROOT, a.out) if a.out else rundir.rstrip('/') + '.json'

    if not a.assemble_only:
        cases = a.cases
        if cases == ['all']:
            cases = sorted(os.path.basename(p)[:-5] for p in
                           glob.glob(os.path.join(ROOT, 'pkg', 'data', 'case_[0-9][0-9][0-9].json')))
        jobs = [(c, k, d, p, a.algo, rundir, e)
                for c in cases for k in a.cores for d in a.divs for p in a.problem
                for e in ((x for x in a.keffs if x < k) if a.keffs else [k])]
        todo = [j for j in jobs
                if not os.path.exists(os.path.join(rundir, tag(j[0], j[1], j[4], j[2], j[3], j[6]) + '.json'))]
        # 大用例先跑：慢作业与小作业重叠，避免长尾全堆在最后
        size = {c: os.path.getsize(os.path.join(ROOT, 'pkg', 'data', c + '.json')) for c in cases}
        todo.sort(key=lambda j: -size[j[0]])
        print(f'总作业 {len(jobs)}，已完成 {len(jobs)-len(todo)}，本次执行 {len(todo)}', flush=True)
        done = 0
        with ProcessPoolExecutor(max_workers=a.j) as ex:
            futs = [ex.submit(one, j) for j in todo]
            for f in as_completed(futs):
                done += 1
                if done % 100 == 0:
                    print(f'  进度 {done}/{len(todo)}  {time.strftime("%H:%M:%S")}', flush=True)

    rows = assemble(rundir, outfile)
    errs = [r for r in rows if 'err' in r]
    print(f'汇总 {len(rows)} 条 -> {outfile}，失败 {len(errs)}')
    for e in errs[:5]:
        print(' ERR', e['case'], e['k'], e['algo'], e['div'], str(e['err'])[:140])
