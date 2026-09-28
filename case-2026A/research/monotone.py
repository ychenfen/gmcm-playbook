# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方公布为准）
"""核数单调补齐：k 核结果不应劣于用更少核的方案。

题目允许 core_schedules 的内层数组为空，因此 k' 核的方案补 k-k' 个空核就是合法的 k 核方案。
对每个 (问题, 用例, k)，若交付结果中某个 k' < k 的 makespan 更小，就把该 k' 方案补空核后交给
官方评估器重评（补空核后 makespan 不一定与 k' 完全相同，必须以评估器为准）。

输入：deliverables/plans/ 与 appendix；输出：runs/mono/{case}_k{k}_p{P}_from{k'}.json 与 runs/mono/plans/。
失败的评估记录错误信息，不静默丢弃。断点续跑。
"""
import json, os, sys, csv, argparse, time
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crosseval import evaluate_full, canon
from sweep2 import pad

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
D = os.path.join(ROOT, 'deliverables')
OUTD = os.path.join(ROOT, 'runs', 'mono')


def delivered_makespans():
    ms = {}
    for p in (1, 2):
        for r in csv.DictReader(open(os.path.join(D, f'appendix_p{p}.csv'))):
            for k in (2, 3, 4, 5):
                ms[(p, r['case'], k)] = int(r[f'makespan_k{k}'])
    for r in csv.DictReader(open(os.path.join(D, 'appendix_p3.csv'))):
        k = int(r['k'])
        ms[(3, r['case'], k)] = int(r['cache_makespan'])
        if k == 1:                                   # 问题2 的 1 核最优只出现在问题3 附录的无L2 列
            ms[(2, r['case'], 1)] = int(r['noL2_makespan'])
    return ms


def jobs_needed(ms):
    out = []
    cases = sorted({c for _, c, _ in ms})
    for p in (1, 2, 3):
        lo = 2 if p == 1 else 1
        for c in cases:
            for k in range(max(lo + 1, 2), 6):
                cur = ms.get((p, c, k))
                if cur is None:
                    continue
                for kp in range(lo, k):
                    src = ms.get((p, c, kp))
                    plan = os.path.join(D, 'plans', f'p{p}_k{kp}_{c}.json')
                    if src is not None and src < cur and os.path.exists(plan):
                        out.append((p, c, k, kp, plan, src, cur))
    return out


def out_name(p, c, k, kp, plan_path):
    """文件名带来源方案的哈希：低核数方案更新后会生成新记录，旧记录仍是合法的历史候选。"""
    h = canon(pad(json.load(open(plan_path)), k))
    return f'{c}_k{k}_p{p}_from{kp}_{h[:12]}', h


def job(args):
    p, c, k, kp, plan_path, src_ms, cur_ms = args
    name, h = out_name(p, c, k, kp, plan_path)
    legacy = os.path.join(OUTD, f'{c}_k{k}_p{p}_from{kp}.json')      # 早期无哈希命名的记录
    if os.path.exists(legacy):
        try:
            if json.load(open(legacy)).get('hash') == h:
                return legacy, 'skip'
        except Exception:
            pass
    out = os.path.join(OUTD, name + '.json')
    if os.path.exists(out):
        return out, 'skip'
    plan = pad(json.load(open(plan_path)), k)
    pp = os.path.join(OUTD, 'plans', name + '.json')
    json.dump(plan, open(pp + '.tmp', 'w')); os.replace(pp + '.tmp', pp)
    m, err = evaluate_full(c, plan, p)
    rec = {'case': c, 'k': k, 'problem': p, 'from_k': kp, 'plan': os.path.relpath(pp, ROOT), 'hash': h,
           'source_makespan_at_from_k': src_ms, 'delivered_makespan_at_k': cur_ms, 'makespan': m}
    if err:
        rec['err'] = err
    json.dump(rec, open(out + '.tmp', 'w')); os.replace(out + '.tmp', out)
    return out, 'done'


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('-j', type=int, default=6)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    os.makedirs(os.path.join(OUTD, 'plans'), exist_ok=True)
    js = jobs_needed(delivered_makespans())
    size = {c: os.path.getsize(os.path.join(ROOT, 'pkg', 'data', c + '.json')) for _, c, *_ in js}
    js.sort(key=lambda j: -size[j[1]])
    print(f'补齐作业 {len(js)} 个（问题1 {sum(j[0]==1 for j in js)}，问题2 {sum(j[0]==2 for j in js)}，'
          f'问题3 {sum(j[0]==3 for j in js)}），并行 {a.j}', flush=True)
    if a.dry_run:
        sys.exit(0)
    done, failed = 0, []
    with ProcessPoolExecutor(max_workers=a.j) as ex:
        futs = {ex.submit(job, j): j for j in js}
        for f in as_completed(futs):
            done += 1
            try:
                f.result()
            except Exception as exc:
                failed.append((futs[f][:4], f'{type(exc).__name__}: {exc}'))
            if done % 20 == 0:
                print(f'  进度 {done}/{len(js)}  {time.strftime("%H:%M:%S")}', flush=True)
    missing = [j for j in js if not (os.path.exists(os.path.join(OUTD, out_name(j[0], j[1], j[2], j[3], j[4])[0] + '.json'))
               or os.path.exists(os.path.join(OUTD, f'{j[1]}_k{j[2]}_p{j[0]}_from{j[3]}.json')))]
    print(f'==== 补齐结束：作业 {len(js)}，落盘缺失 {len(missing)}，异常 {len(failed)} ====', flush=True)
    for x in failed[:10]:
        print('  异常', x, flush=True)
