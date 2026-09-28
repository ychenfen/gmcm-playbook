# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方公布为准）
"""终版交叉复评：问题2、问题3 的最终获胜方案互相交给对方的官方评估器。

问题2（无L2）与问题3（只读Cache）同属场景B，方案可以互换。若一方的获胜方案从未在另一方评估过，
"各自最优"口径下就可能出现只读Cache 比无L2 还慢的假象（候选池不对称，而非缓存本身的作用）。
本脚本补齐这一步，记录写入 runs/xe/（与 crosseval.py 同格式），由 finalize.py 统一纳入候选。
已存在同哈希、同目标问题的记录则跳过。
"""
import json, os, sys, glob, argparse, time
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crosseval import evaluate_full, canon

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
D = os.path.join(ROOT, 'deliverables')
OUTD = os.path.join(ROOT, 'runs', 'xe')


def known_pairs():
    """已评估过的 (用例, 核数, 目标问题, 方案哈希)。"""
    seen = set()
    for f in glob.glob(os.path.join(OUTD, 'case_*.json')):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if r.get('makespan') and not r.get('err'):
            seen.add((r['case'], r['k'], r['problem'], r['hash']))
    return seen


def jobs():
    seen = known_pairs()
    out = []
    for f in sorted(glob.glob(os.path.join(D, 'plans', 'p[23]_k*_case_*.json'))):
        b = os.path.basename(f)[:-5].split('_')
        p, k, case = int(b[0][1:]), int(b[1][1:]), '_'.join(b[2:])
        target = 3 if p == 2 else 2
        plan = json.load(open(f))
        h = canon(plan)
        other = os.path.join(D, 'plans', f'p{target}_k{k}_{case}.json')
        if os.path.exists(other) and canon(json.load(open(other))) == h:
            continue                                  # 两边已是同一方案
        if (case, k, target, h) in seen:
            continue
        out.append((case, k, target, p, h, f))
    return out


def job(a):
    case, k, target, src_p, h, src_file = a
    out = os.path.join(OUTD, f'{case}_k{k}_p{target}_{h[:12]}.json')
    if os.path.exists(out):
        return 'skip'
    plan = json.load(open(src_file))
    pp = os.path.join(OUTD, 'plans', h + '.json')
    if not os.path.exists(pp):
        json.dump(plan, open(pp + '.tmp', 'w')); os.replace(pp + '.tmp', pp)
    m, err = evaluate_full(case, plan, target)
    rec = {'case': case, 'k': k, 'problem': target, 'hash': h, 'plan': os.path.relpath(pp, ROOT),
           'origins': [f'final_p{src_p}_20260924'], 'makespan': m}
    if err:
        rec['err'] = err
    json.dump(rec, open(out + '.tmp', 'w')); os.replace(out + '.tmp', out)
    return 'done'


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('-j', type=int, default=6)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    js = jobs()
    size = {j[0]: os.path.getsize(os.path.join(ROOT, 'pkg', 'data', j[0] + '.json')) for j in js}
    js.sort(key=lambda j: -size[j[0]])
    print(f'终版交叉复评 {len(js)} 个（问题2→问题3 {sum(j[2]==3 for j in js)}，问题3→问题2 {sum(j[2]==2 for j in js)}）', flush=True)
    if a.dry_run:
        sys.exit(0)
    failed, done = [], 0
    with ProcessPoolExecutor(max_workers=a.j) as ex:
        futs = {ex.submit(job, j): j for j in js}
        for f in as_completed(futs):
            done += 1
            try:
                f.result()
            except Exception as exc:
                failed.append((futs[f][:3], f'{type(exc).__name__}: {exc}'))
            if done % 50 == 0:
                print(f'  进度 {done}/{len(js)}  {time.strftime("%H:%M:%S")}', flush=True)
    missing = [j for j in js if not os.path.exists(os.path.join(OUTD, f'{j[0]}_k{j[1]}_p{j[2]}_{j[4][:12]}.json'))]
    print(f'==== 终版交叉复评结束：作业 {len(js)}，缺失 {len(missing)}，异常 {len(failed)} ====', flush=True)
    for x in failed[:10]:
        print('  异常', x, flush=True)
