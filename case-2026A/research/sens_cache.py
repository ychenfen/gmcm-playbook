# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""问题3 敏感性分析：L2 容量与带宽对 makespan 的影响（仅用于分析，官方结果一律用固定 config）。

对每个 (用例, 核数) 取问题3当前最优方案，固定方案，只改 config 的 [problem_3] 两个参数重评：
  容量扫描：带宽固定 250，容量 ∈ {256K, 512K, 1M(官方), 2M, 4M, 16M, 1G≈无限}
  带宽扫描：容量固定 1M，带宽 ∈ {30, 60, 125, 250(官方), 500, 1000}
诊断的预测：容量缺失≈0 → 容量曲线应当几乎平；收益主要受重复读机会与 DDR 负载限制。
结果逐作业落盘 runs/sens/，断点续跑。
"""
import json, os, sys, glob, argparse, subprocess, tempfile, time
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from finalize import load_candidates, build, ROOT, PY

BASE = os.path.join(ROOT, 'pkg', 'data', 'config.txt')
OUTD = os.path.join(ROOT, 'runs', 'sens')
CAPS = [262144, 524288, 1048576, 2097152, 4194304, 16777216, 1073741824]
BWS = [30, 60, 125, 250, 500, 1000]


def configs():
    base = open(BASE).read()
    out = []
    for cap in CAPS:
        out.append(('cap', cap, 250, cap))
    for bw in BWS:
        out.append(('bw', bw, bw, 1048576))
    res = []
    os.makedirs(os.path.join(OUTD, 'cfg'), exist_ok=True)
    for kind, val, bw, cap in out:
        txt = base.replace('cache_capacity_bytes 1048576', f'cache_capacity_bytes {cap}') \
                  .replace('cache_bandwidth_bytes_per_cycle 250', f'cache_bandwidth_bytes_per_cycle {bw}')
        p = os.path.join(OUTD, 'cfg', f'{kind}_{val}.txt')
        open(p, 'w').write(txt)
        res.append((kind, val, p))
    return res


def job(t):
    case, k, cand, kind, val, cfg = t
    out = os.path.join(OUTD, f'{case}_k{k}_{kind}_{val}.json')
    if os.path.exists(out):
        return
    g = json.load(open(os.path.join(ROOT, 'pkg', 'data', case + '.json')))
    plan = build(g, k, cand)
    with tempfile.TemporaryDirectory() as td:
        pp = os.path.join(td, 'p.json'); json.dump(plan, open(pp, 'w'))
        r = subprocess.run([PY, os.path.join(ROOT, 'pkg/code/multicore_cut_evaluate_problem_3.py'),
                            os.path.join(ROOT, 'pkg/data', case + '.json'), pp, '--config', cfg,
                            '-o', td + '/r.json', '--trace-output', td + '/t.json', '--log-output', td + '/l.txt'],
                           capture_output=True, text=True, timeout=7200)
        rec = {'case': case, 'k': k, 'kind': kind, 'val': val, 'source': cand}
        if r.returncode:
            rec['err'] = (r.stderr or r.stdout)[-300:]
        else:
            res = json.load(open(td + '/r.json'))
            cs = res['cache_stats']
            rec.update(makespan=res['makespan'], hit_rate=cs.get('hit_rate'),
                       hit_bytes=cs.get('hit_bytes'), miss_bytes=cs.get('miss_bytes'))
    json.dump(rec, open(out + '.tmp', 'w')); os.replace(out + '.tmp', out)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--cores', nargs='+', type=int, default=[4, 5])
    ap.add_argument('-j', type=int, default=24)
    a = ap.parse_args()
    os.makedirs(OUTD, exist_ok=True)
    cfgs = configs()
    cand = load_candidates()
    cases = sorted(os.path.basename(p)[:-5] for p in
                   glob.glob(os.path.join(ROOT, 'pkg', 'data', 'case_[0-9][0-9][0-9].json')))
    size = {c: os.path.getsize(os.path.join(ROOT, 'pkg', 'data', c + '.json')) for c in cases}
    ts = []
    for c in sorted(cases, key=lambda c: -size[c]):
        for k in a.cores:
            cs = cand.get((3, c, k))
            if not cs:
                continue
            best = min(cs, key=lambda x: x['makespan'])
            for kind, val, p in cfgs:
                ts.append((c, k, best, kind, val, p))
    print(f'敏感性作业 {len(ts)} 个，并行 {a.j}', flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=a.j) as ex:
        for f in as_completed([ex.submit(job, t) for t in ts]):
            done += 1
            if done % 200 == 0:
                print(f'  进度 {done}/{len(ts)}  {time.strftime("%H:%M:%S")}', flush=True)
    print('==== 敏感性分析完成 ====', flush=True)
