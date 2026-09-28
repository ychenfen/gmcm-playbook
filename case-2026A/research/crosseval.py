# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""交叉复评（采纳 Codex 19:34 交接建议 A）：各问题已有的获胜方案互相交给其他问题的官方评估器。

动机：case_061 3 核，问题3 原始最优是 phase（36,250），压过了 LPT（36,568）；可 LPT 合并后的问题2 获胜方案
放到问题3 评估器下是 28,368（−21.7%）。"只从原始最优起点后处理"会漏解；问题2、3 同属场景B，方案可直接互换。

对每个 (用例, 核数)：收集问题1/2/3 各来源的最优方案（扫描最优按算法各取一个、成组合并各轮获胜、局部搜索获胜），
按规范化 JSON 内容的 SHA-256 去重，逐个交给目标问题评估器（默认问题2、3）。已知的 (方案, 问题) 不重复评估。
结果 runs/xe/{case}_k{k}_p{P}_{hash12}.json，方案 runs/xe/plans/{hash}.json；失败记录错误信息，不静默丢弃。
"""
import json, os, sys, glob, hashlib, argparse, tempfile, time, collections
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from finalize import build, ROOT, CFG, PY
from sweep2 import make_plan, pad
import subprocess

OUTD = os.path.join(ROOT, 'runs', 'xe')


def canon(plan):
    s = json.dumps({'node_to_subgraph': {str(k): v for k, v in sorted(plan['node_to_subgraph'].items(), key=lambda x: int(x[0]))},
                    'core_schedules': plan['core_schedules']}, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(s.encode()).hexdigest()


def evaluate_full(case, plan, problem):
    with tempfile.TemporaryDirectory() as td:
        json.dump(plan, open(td + '/p.json', 'w'))
        r = subprocess.run([PY, os.path.join(ROOT, f'pkg/code/multicore_cut_evaluate_problem_{problem}.py'),
                            os.path.join(ROOT, 'pkg/data', case + '.json'), td + '/p.json', '--config', CFG,
                            '-o', td + '/r.json', '--trace-output', td + '/t.json', '--log-output', td + '/l.txt'],
                           capture_output=True, text=True, timeout=7200)
        if r.returncode:
            return None, (r.stderr or r.stdout)[-300:]
        return json.load(open(td + '/r.json'))['makespan'], None


def sources(case, k):
    """(描述, 已知{问题: makespan}, 取方案函数)。"""
    out = []
    best = {}
    for f in glob.glob(os.path.join(ROOT, 'runs/pf', f'{case}_k{k}_*.json')):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if 'err' in r or not r.get('makespan') or r['k'] != k:
            continue
        key = (r['problem'], r['algo'])
        if key not in best or r['makespan'] < best[key]['makespan']:
            best[key] = r
    for (p, algo), r in best.items():
        c = {'src': 'sweep', 'algo': algo, 'div': r['div'], 'keff': r.get('keff') or k}
        out.append((f'sweep:p{p}:{algo}{r["div"]:g}', {p: r['makespan']}, c))
    for d in sorted(glob.glob(os.path.join(ROOT, 'runs', 'co*'))):
        for p in (1, 2, 3):
            f = os.path.join(d, f'{case}_k{k}_p{p}.json')
            if os.path.exists(f):
                r = json.load(open(f))
                if r.get('plan'):
                    out.append((f'{os.path.basename(d)}:p{p}:{r["best_name"]}', {p: r['best_makespan']},
                                {'plan': os.path.join(ROOT, r['plan'])}))
    for f in glob.glob(os.path.join(ROOT, 'runs/ls2', f'{case}_k{k}_p*_s*.json')):
        r = json.load(open(f))
        pl = os.path.join(ROOT, 'runs/ls2/plans', os.path.basename(f))
        if r.get('makespan') and os.path.exists(pl):
            out.append((f'ls2:p{r["problem"]}:s{r["seed"]}', {r['problem']: r['makespan']}, {'plan': pl}))
    return out


def job(args):
    case, k, targets = args
    g = json.load(open(os.path.join(ROOT, 'pkg/data', case + '.json')))
    uniq = collections.OrderedDict()                     # 哈希 -> [方案, 描述列表, 已知]
    for desc, known, c in sources(case, k):
        try:
            plan = json.load(open(c['plan'])) if 'plan' in c else pad(make_plan(g, c['keff'], c['algo'], c['div']), k)
        except Exception:
            continue
        h = canon(plan)
        if h not in uniq:
            uniq[h] = [plan, [], {}]
        uniq[h][1].append(desc)
        uniq[h][2].update(known)
    n_new = 0
    for h, (plan, descs, known) in uniq.items():
        pp = os.path.join(OUTD, 'plans', h + '.json')
        if not os.path.exists(pp):
            json.dump(plan, open(pp + '.tmp', 'w')); os.replace(pp + '.tmp', pp)
        for p in targets:
            out = os.path.join(OUTD, f'{case}_k{k}_p{p}_{h[:12]}.json')
            if os.path.exists(out) or p in known:
                continue
            m, err = evaluate_full(case, plan, p)
            n_new += 1
            rec = {'case': case, 'k': k, 'problem': p, 'hash': h, 'plan': os.path.relpath(pp, ROOT),
                   'origins': descs, 'makespan': m}
            if err:
                rec['err'] = err
            json.dump(rec, open(out + '.tmp', 'w')); os.replace(out + '.tmp', out)
    return case, k, len(uniq), n_new


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--cores', nargs='+', type=int, default=[1, 2, 3, 4, 5])
    ap.add_argument('--targets', nargs='+', type=int, default=[2, 3])
    ap.add_argument('--cases', nargs='+', default=['all'])
    ap.add_argument('-j', type=int, default=16)
    a = ap.parse_args()
    os.makedirs(os.path.join(OUTD, 'plans'), exist_ok=True)
    cases = a.cases if a.cases != ['all'] else sorted(
        os.path.basename(p)[:-5] for p in glob.glob(os.path.join(ROOT, 'pkg/data/case_[0-9][0-9][0-9].json')))
    size = {c: os.path.getsize(os.path.join(ROOT, 'pkg/data', c + '.json')) for c in cases}
    jobs = [(c, k, a.targets) for c in sorted(cases, key=lambda c: -size[c]) for k in a.cores]
    print(f'交叉复评作业 {len(jobs)} 个，目标问题 {a.targets}，并行 {a.j}', flush=True)
    done, failed, tot_new = 0, [], 0
    with ProcessPoolExecutor(max_workers=a.j) as ex:
        futs = {ex.submit(job, j): j for j in jobs}
        for f in as_completed(futs):
            done += 1
            try:
                _, _, _, n = f.result(); tot_new += n
            except Exception as exc:
                failed.append((futs[f][0], futs[f][1], f'{type(exc).__name__}: {exc}'))
            if done % 50 == 0:
                print(f'  进度 {done}/{len(jobs)}  新评估 {tot_new}  {time.strftime("%H:%M:%S")}', flush=True)
    print(f'==== 交叉复评结束：作业 {len(jobs)}，新评估 {tot_new}，异常 {len(failed)} ====', flush=True)
    for x in failed[:10]:
        print('  异常', x, flush=True)
