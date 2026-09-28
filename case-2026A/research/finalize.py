# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
# 人工智能工具：OpenAI Codex（ChatGPT 桌面应用），版本/型号：【待团队按会话记录填写】，开发机构：OpenAI，版本发布日期：【待填写】
"""终版复评：为每个 (问题, 用例, 核数) 选出最优方案，用官方评估器重新评一遍并存档。

论文附录里的每个数字都来自这一步的官方评估器输出，不引用扫描阶段记录的值，
复评值与扫描记录不一致的会被单独列出（可复现性检查）。

产物（deliverables/）：
  plans/p{P}_k{K}_{case}.json   提交用的方案文件（node_to_subgraph + core_schedules）
  evals/p{P}_k{K}_{case}.json   官方评估器输出的摘要（makespan、搬运量、缓存统计、方案来源）
  evals/p2x_k{K}_{case}.json    问题3所选方案放到无L2（问题2评估器）下的配对复评
  summary.json / appendix_p{1,2,3}.csv

口径：
  问题1/2：k=1 加速比按题目定义为 1；k 核加速比 = 单核基准 makespan / k 核 makespan。
  问题3：无L2 = 场景B（问题2评估器），只读Cache = 问题3评估器。
         主口径"各自最优"：无L2 取问题2最优，只读Cache 取问题3最优；
         辅助口径"同一方案"：问题3所选方案在两种配置下的 makespan 之比，只反映缓存本身的作用。
"""
import json, os, sys, re, glob, csv, argparse, subprocess, tempfile, statistics, collections, time, hashlib
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep2 import make_plan, pad

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
PY = sys.executable
CFG = os.path.join(ROOT, 'pkg', 'data', 'config.txt')
OUT = os.path.join(ROOT, 'deliverables')


def singlecore():
    ms = {}
    for f in glob.glob(os.path.join(ROOT, 'runs', 'singlecore', 'case_[0-9][0-9][0-9].log')):
        m = re.search(r'makespan=([\d,]+)', open(f).read())
        if m:
            ms[os.path.basename(f)[:-4]] = int(m.group(1).replace(',', ''))
    return ms


def load_candidates():
    """所有扫描与局部搜索结果，按 (问题, 用例, 核数) 分组。"""
    cand = collections.defaultdict(list)
    for f in glob.glob(os.path.join(ROOT, 'runs', 'pf', '*.json')):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if 'err' in r or not r.get('makespan'):
            continue
        cand[(r['problem'], r['case'], r['k'])].append(
            {'src': 'sweep', 'algo': r['algo'], 'div': r['div'], 'keff': r.get('keff') or r['k'],
             'makespan': r['makespan']})
    for f in glob.glob(os.path.join(ROOT, 'runs', 'ls2', 'case_*.json')):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        plan = os.path.join(ROOT, 'runs', 'ls2', 'plans', os.path.basename(f))
        if 'err' in r or not r.get('makespan') or not os.path.exists(plan):
            continue
        cand[(r['problem'], r['case'], r['k'])].append(
            {'src': 'localsearch', 'plan': plan, 'seed': r['seed'], 'makespan': r['makespan']})
    for f in glob.glob(os.path.join(ROOT, 'runs', 'co*', 'case_*.json')):   # 成组合并后处理（各轮）
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if r.get('plan') and r.get('best_makespan') and r['best_makespan'] < (r.get('base_makespan') or 1e30):
            cand[(r['problem'], r['case'], r['k'])].append(
                {'src': 'coarsen', 'plan': os.path.join(ROOT, r['plan']), 'variant': r['best_name'],
                 'makespan': r['best_makespan']})
    for f in glob.glob(os.path.join(ROOT, 'runs', 'xe', 'case_*.json')):     # 交叉复评
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if r.get('makespan') and not r.get('err'):
            cand[(r['problem'], r['case'], r['k'])].append(
                {'src': 'crosseval', 'plan': os.path.join(ROOT, r['plan']), 'hash': r['hash'][:12],
                 'makespan': r['makespan']})
    for f in glob.glob(os.path.join(ROOT, 'runs', 'mono', 'case_*.json')):   # 核数单调补齐（少核方案补空核）
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if r.get('makespan') and not r.get('err'):
            cand[(r['problem'], r['case'], r['k'])].append(
                {'src': 'monotone', 'plan': os.path.join(ROOT, r['plan']), 'from_k': r['from_k'],
                 'makespan': r['makespan']})
    return cand


def src_label(c):
    """统一来源标签：扫描方案用算法名，其余（局部搜索、成组合并、交叉复评）用来源类型。"""
    return c.get('algo') if c.get('src') == 'sweep' else c.get('src', 'unknown')


def atomic_json(path, data):
    """独立临时文件，成功写完后替换；异常不留下半个 JSON。"""
    fd, tmp = tempfile.mkstemp(prefix='.finalize-', suffix='.tmp', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def plan_hash(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_json(path):
    with open(path) as fh:
        return json.load(fh)


def task_tag(task):
    kind, problem, case, k, _ = task
    return f"{'p2x' if kind == 'pair' else f'p{problem}'}_k{k}_{case}"


def build(g, k, c):
    if 'plan' in c:
        return json.load(open(c['plan']))
    return pad(make_plan(g, c['keff'], c['algo'], c['div']), k)


def evaluate(case, plan, problem):
    gpath = os.path.join(ROOT, 'pkg', 'data', case + '.json')
    with tempfile.TemporaryDirectory() as td:
        pp = os.path.join(td, 'plan.json')
        json.dump(plan, open(pp, 'w'))
        ev = os.path.join(ROOT, 'pkg', 'code', f'multicore_cut_evaluate_problem_{problem}.py')
        r = subprocess.run([PY, ev, gpath, pp, '--config', CFG, '-o', os.path.join(td, 'r.json'),
                            '--trace-output', os.path.join(td, 't.json'),
                            '--log-output', os.path.join(td, 'l.txt')],
                           capture_output=True, text=True, timeout=7200)
        if r.returncode != 0:
            return {'err': (r.stderr or r.stdout)[-400:]}
        res = json.load(open(os.path.join(td, 'r.json')))
    cs = res.get('cache_stats') or {}
    return {'makespan': res['makespan'],
            'data_movement_bytes': res.get('data_movement_bytes'),
            'cache': {k: cs.get(k) for k in ('hit_rate', 'hits', 'accesses', 'hit_bytes', 'miss_bytes')}
            if cs else None}


def job(task):
    kind, problem, case, k, c = task          # kind: 'main' 或 'pair'（问题3方案放到问题2评估器下）
    tag = task_tag(task)
    evf = os.path.join(OUT, 'evals', tag + '.json')
    plan_file = os.path.join(OUT, 'plans', tag + '.json')
    g = read_json(os.path.join(ROOT, 'pkg', 'data', case + '.json'))
    plan = build(g, k, c)
    digest = plan_hash(plan)
    if os.path.exists(evf):
        try:
            old = read_json(evf)
            good = old.get('source') == c and old.get('makespan', 0) > 0 and not old.get('err')
            if kind == 'main':
                good = (good and old.get('reproduced') is True
                        and old['makespan'] == c['makespan']
                        and plan_hash(read_json(plan_file)) == digest)
            else:
                # 旧配对记录没有方案哈希，重评一次，不能仅凭来源路径复用。
                good = good and old.get('plan_sha256') == digest
            if good:
                if old.get('plan_sha256') != digest:
                    old['plan_sha256'] = digest
                    atomic_json(evf, old)
                return tag, 'skip'
        except Exception:
            pass
    rec = evaluate(case, plan, 2 if kind == 'pair' else problem)
    if rec.get('err') or not rec.get('makespan'):
        raise RuntimeError(f"{tag}: official evaluation failed: {rec.get('err', 'missing makespan')}")
    if kind == 'main' and rec['makespan'] != c['makespan']:
        raise RuntimeError(f"{tag}: makespan mismatch {rec['makespan']} != {c['makespan']}")
    rec.update(case=case, k=k, problem=problem, kind=kind, source=c,
               n_subgraphs=len(set(plan['node_to_subgraph'].values())), plan_sha256=digest)
    if kind == 'main' and 'makespan' in rec:
        rec['reproduced'] = rec['makespan'] == c['makespan']
    if kind == 'main':
        atomic_json(plan_file, plan)
    atomic_json(evf, rec)
    return tag, 'done'


def tasks(cand, cases):
    out = []
    missing = []
    for case in cases:
        for problem, ks in ((1, range(2, 6)), (2, range(1, 6)), (3, range(1, 6))):
            for k in ks:
                cs = cand.get((problem, case, k))
                if not cs:
                    missing.append((problem, case, k))
                    continue
                best = min(cs, key=lambda c: c['makespan'])
                out.append(('main', problem, case, k, best))
                if problem == 3:
                    out.append(('pair', 3, case, k, best))
    if missing:
        raise ValueError(f'missing candidate groups ({len(missing)}): {missing[:20]}')
    return out


def init_worker(output):
    global OUT
    OUT = output


def run_tasks(ts, workers, executor_type=ProcessPoolExecutor):
    failures, counts = [], collections.Counter()
    with executor_type(max_workers=workers, initializer=init_worker, initargs=(OUT,)) as ex:
        futs = {ex.submit(job, t): t for t in ts}
        for done, f in enumerate(as_completed(futs), 1):
            try:
                _, state = f.result()
                counts[state] += 1
            except Exception as exc:
                failures.append({'task': task_tag(futs[f]), 'error': f'{type(exc).__name__}: {exc}'})
            if done % 100 == 0:
                print(f'  进度 {done}/{len(ts)}  新评 {counts["done"]}  复用 {counts["skip"]} '
                      f'异常 {len(failures)}  {time.strftime("%H:%M:%S")}', flush=True)
    return failures, dict(counts)


def validate_results(ts):
    """主结果与配对结果都必须对应本轮冻结的选择，旧文件不能冒充本轮完成。"""
    issues = []
    for task in ts:
        kind, problem, case, k, source = task
        tag = task_tag(task)
        try:
            r = read_json(os.path.join(OUT, 'evals', tag + '.json'))
            if (r.get('source') != source or r.get('err') or not r.get('makespan')
                    or not r.get('plan_sha256')
                    or (r.get('kind'), r.get('problem'), r.get('case'), r.get('k')) != (kind, problem, case, k)):
                raise ValueError('missing, failed or stale evaluation')
            if kind == 'main':
                if r.get('reproduced') is not True or r['makespan'] != source['makespan']:
                    raise ValueError('main makespan mismatch')
                saved = read_json(os.path.join(OUT, 'plans', tag + '.json'))
                if plan_hash(saved) != r['plan_sha256']:
                    raise ValueError('saved plan hash mismatch')
            if 'plan' in source and plan_hash(read_json(source['plan'])) != r['plan_sha256']:
                raise ValueError('source plan changed since evaluation')
            if kind == 'pair':
                main = read_json(os.path.join(OUT, 'evals', f'p3_k{k}_{case}.json'))
                if main.get('plan_sha256') != r['plan_sha256']:
                    raise ValueError('P2/P3 paired plan mismatch')
        except Exception as exc:
            issues.append({'task': tag, 'error': f'{type(exc).__name__}: {exc}'})
    return issues


def summarize(cases, expected_tasks=None):
    expected_tasks = expected_tasks if expected_tasks is not None else tasks(load_candidates(), cases)
    issues = validate_results(expected_tasks)
    if issues:
        raise ValueError(f'refusing stale/incomplete summary: {issues[:10]}')
    sc = singlecore()
    if any(c not in sc for c in cases):
        raise ValueError('missing singlecore baseline')
    ev = {}
    expected_tags = {task_tag(t) for t in expected_tasks}
    for f in glob.glob(os.path.join(OUT, 'evals', '*.json')):
        r = read_json(f)
        if os.path.basename(f)[:-5] in expected_tags:
            ev[os.path.basename(f)[:-5]] = r
    get = lambda p, k, c: ev.get(f'{p}_k{k}_{c}', {}).get('makespan')
    summ = {'n_cases': len(cases), 'speedup': {}, 'p3': {}, 'reproducibility': {}}

    for p in (1, 2):
        curve, rows = {1: 1.0}, []
        for k in range(2, 6):
            sp = [sc[c] / get(f'p{p}', k, c) for c in cases if get(f'p{p}', k, c) and c in sc]
            curve[k] = statistics.mean(sp) if sp else None
            summ.setdefault('geomean', {}).setdefault(p, {})[k] = (
                statistics.geometric_mean(sp) if sp else None)
            summ.setdefault('n', {}).setdefault(p, {})[k] = len(sp)
        summ['speedup'][p] = curve
        with open(os.path.join(OUT, f'appendix_p{p}.csv'), 'w', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(['case', 'singlecore_makespan'] +
                       [f'{h}_k{k}' for k in range(2, 6) for h in ('makespan', 'added_bytes', 'speedup')])
            for c in cases:
                row = [c, sc.get(c)]
                for k in range(2, 6):
                    r = ev.get(f'p{p}_k{k}_{c}', {})
                    m = r.get('makespan')
                    row += [m, (r.get('data_movement_bytes') or {}).get('added_copy_bytes'),
                            round(sc[c] / m, 4) if m and c in sc else None]
                w.writerow(row)

    p3 = {}
    with open(os.path.join(OUT, 'appendix_p3.csv'), 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['case', 'k', 'noL2_makespan', 'cache_makespan', 'cache_speedup_best',
                    'cache_speedup_sameplan', 'noL2_added_bytes', 'cache_added_bytes', 'cache_hit_rate'])
        for k in range(1, 6):
            best_ratio, pair_ratio, hit = [], [], []
            for c in cases:
                a, b = ev.get(f'p2_k{k}_{c}', {}), ev.get(f'p3_k{k}_{c}', {})
                x = ev.get(f'p2x_k{k}_{c}', {})
                if not (a.get('makespan') and b.get('makespan')):
                    continue
                rb = a['makespan'] / b['makespan']
                rp = x['makespan'] / b['makespan'] if x.get('makespan') else None
                hr = (b.get('cache') or {}).get('hit_rate')
                best_ratio.append(rb)
                if rp: pair_ratio.append(rp)
                if hr is not None: hit.append(hr)
                w.writerow([c, k, a['makespan'], b['makespan'], round(rb, 4),
                            round(rp, 4) if rp else None,
                            (a.get('data_movement_bytes') or {}).get('added_copy_bytes'),
                            (b.get('data_movement_bytes') or {}).get('added_copy_bytes'),
                            round(hr, 4) if hr is not None else None])
            p3[k] = {'n': len(best_ratio),
                     'cache_speedup_best': statistics.mean(best_ratio) if best_ratio else None,
                     'cache_speedup_sameplan': statistics.mean(pair_ratio) if pair_ratio else None,
                     'hit_rate_mean': statistics.mean(hit) if hit else None,
                     'noL2_vs_single': statistics.mean(
                         [sc[c] / ev[f'p2_k{k}_{c}']['makespan'] for c in cases
                          if ev.get(f'p2_k{k}_{c}', {}).get('makespan') and c in sc]) if best_ratio else None,
                     'cache_vs_single': statistics.mean(
                         [sc[c] / ev[f'p3_k{k}_{c}']['makespan'] for c in cases
                          if ev.get(f'p3_k{k}_{c}', {}).get('makespan') and c in sc]) if best_ratio else None}
    summ['p3'] = p3

    mains = [r for r in ev.values() if r.get('kind') == 'main']
    summ['reproducibility'] = {
        'evaluated': len(mains),
        'errors': [f"p{r['problem']}_k{r['k']}_{r['case']}" for r in mains if 'err' in r],
        'mismatch': [f"p{r['problem']}_k{r['k']}_{r['case']}" for r in mains if r.get('reproduced') is False],
        'source_mix': collections.Counter(src_label(r['source']) for r in mains if 'source' in r),
        'paired_evaluated': sum(r.get('kind') == 'pair' for r in ev.values()),
        'selection_verified': True,
    }
    json.dump(summ, open(os.path.join(OUT, 'summary.json'), 'w'), indent=1, ensure_ascii=False)
    return summ


def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', nargs='+', default=['all'])
    ap.add_argument('-j', type=int, default=10)
    ap.add_argument('--summary-only', action='store_true')
    ap.add_argument('--out', default=OUT, help='隔离复评目录；验收通过后再提升为正式交付')
    a = ap.parse_args()
    OUT = os.path.abspath(a.out)
    for d in ('plans', 'evals'):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    cases = a.cases
    if cases == ['all']:
        cases = sorted(os.path.basename(p)[:-5] for p in
                       glob.glob(os.path.join(ROOT, 'pkg', 'data', 'case_[0-9][0-9][0-9].json')))
    ts = tasks(load_candidates(), cases)
    atomic_json(os.path.join(OUT, 'selected_tasks.json'), ts)
    atomic_json(os.path.join(OUT, 'finalize_status.json'),
                {'verified': False, 'phase': 'running', 'expected': len(ts)})
    failures, counts = [], {}
    if not a.summary_only:
        size = {c: os.path.getsize(os.path.join(ROOT, 'pkg', 'data', c + '.json')) for c in cases}
        ts.sort(key=lambda t: -size[t[2]])
        print(f'复评作业 {len(ts)} 个，并行 {a.j}', flush=True)
        failures, counts = run_tasks(ts, a.j)
    issues = validate_results(ts)
    status = {'time': time.strftime('%Y-%m-%d %H:%M:%S %z'), 'expected': len(ts),
              'counts': counts, 'worker_errors': failures, 'validation_errors': issues,
              'evaluations_verified': not failures and not issues, 'verified': False}
    atomic_json(os.path.join(OUT, 'finalize_status.json'), status)
    if failures or issues:
        print(json.dumps(status, ensure_ascii=False, indent=1), file=sys.stderr)
        return 2
    s = summarize(cases, ts)
    status.update(verified=True, phase='complete')
    atomic_json(os.path.join(OUT, 'finalize_status.json'), status)
    print(json.dumps({k: s[k] for k in ('speedup', 'p3', 'reproducibility')}, ensure_ascii=False, indent=1,
                     default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
