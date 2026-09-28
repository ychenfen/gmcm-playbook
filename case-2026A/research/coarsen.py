# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""成组合并后处理（采纳 Codex 评审 P3_review_20260923 的方案，候选集原样冻结）。

机制：官方核内调度 _prioritize_task_seq 按子图分桶、桶内恢复 Step1 顺序。保持每个算子的核归属不变，
把每核相邻子图按宽度 w 成组合并，会改变链间执行次序、片上驻留与 COPY_IN 时刻，从而改变缓存命中与 DDR 争用。
case_044/046 上已由官方 CLI 复现：66,992→58,162、82,252→67,552、79,056→75,972、93,464→89,737。

候选：w ∈ {2,4,8,16,32,64,128} × 掩码 {全部核, 仅最后一核, 除最后一核}，共 21 个；原方案作为兜底候选。
非法候选（合并后商图成环等）由官方评估器拒绝并记录。以 makespan 为唯一选择标准，不追求命中率。
每个 (问题, 用例, 核数) 结果落盘 runs/co/，改进时保存方案文件 runs/co/plans/，断点续跑。
"""
import json, os, sys, glob, argparse, tempfile, time
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from finalize import load_candidates, build, ROOT
from localsearch import evaluate

OUTD = os.path.join(ROOT, 'runs', 'co')
WIDTHS = (2, 4, 8, 16, 32, 64, 128)   # 第一轮冻结候选；第二轮用 --widths 与 --outdir 另跑
MODES = ('all', 'last', 'others')


def merge_blocks(plan, width, mode):
    last = len(plan['core_schedules']) - 1
    remap, sched = {}, []
    for core, order in enumerate(plan['core_schedules']):
        active = mode == 'all' or (mode == 'last' and core == last) or (mode == 'others' and core != last)
        stride = width if active else 1
        merged = []
        for i in range(0, len(order), stride):
            merged.append(order[i])
            for s in order[i:i + stride]:
                remap[s] = order[i]
        sched.append(merged)
    return {'node_to_subgraph': {op: remap[sg] for op, sg in plan['node_to_subgraph'].items()},
            'core_schedules': sched}


def job(args):
    problem, case, k, base_c, OUTD, WIDTHS = args
    out = os.path.join(OUTD, f'{case}_k{k}_p{problem}.json')
    if os.path.exists(out):
        return
    gp = os.path.join(ROOT, 'pkg/data', case + '.json')
    g = json.load(open(gp))
    base = build(g, k, base_c)
    rec = {'case': case, 'k': k, 'problem': problem, 'base_source': base_c, 'variants': []}
    with tempfile.TemporaryDirectory() as td:
        m0 = evaluate(gp, base, problem, td)
        rec['base_makespan'] = m0
        best, best_plan, best_name = m0, None, 'base'
        nsg = len(set(base['node_to_subgraph'].values()))
        for w in WIDTHS:
            for mode in MODES:
                if nsg <= 1 or (w >= max(len(o) for o in base['core_schedules']) * 2 and w != WIDTHS[0]):
                    continue                                   # 宽度远超各核子图数时与更小宽度等价，跳过
                plan = merge_blocks(base, w, mode)
                m = evaluate(gp, plan, problem, td)
                rec['variants'].append({'name': f'w{w}_{mode}', 'makespan': m,
                                        'n_subgraphs': len(set(plan['node_to_subgraph'].values()))})
                if m is not None and (best is None or m < best):
                    best, best_plan, best_name = m, plan, f'w{w}_{mode}'
    rec.update(best_makespan=best, best_name=best_name)
    if best_plan is not None:
        pp = os.path.join(OUTD, 'plans', f'{case}_k{k}_p{problem}.json')
        json.dump(best_plan, open(pp, 'w'))
        rec['plan'] = os.path.relpath(pp, ROOT)
    json.dump(rec, open(out + '.tmp', 'w')); os.replace(out + '.tmp', out)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--problems', nargs='+', type=int, default=[3])
    ap.add_argument('--cores', nargs='+', type=int, default=[2, 3, 4, 5])
    ap.add_argument('--cases', nargs='+', default=['all'])
    ap.add_argument('-j', type=int, default=24)
    ap.add_argument('--widths', nargs='+', type=int)
    ap.add_argument('--outdir', default='runs/co')
    ap.add_argument('--max-ops', type=int, default=0, help='>0 时跳过算子数超过该值的用例')
    a = ap.parse_args()
    OUTD = os.path.join(ROOT, a.outdir)
    if a.widths:
        WIDTHS = tuple(a.widths)
    os.makedirs(os.path.join(OUTD, 'plans'), exist_ok=True)
    cand = load_candidates()      # 包含已有 runs/co* 结果 → 第二轮以第一轮合并后的最优为起点
    cases = a.cases if a.cases != ['all'] else sorted(
        os.path.basename(p)[:-5] for p in glob.glob(os.path.join(ROOT, 'pkg/data/case_[0-9][0-9][0-9].json')))
    size = {c: os.path.getsize(os.path.join(ROOT, 'pkg/data', c + '.json')) for c in cases}
    if a.max_ops:
        nops = {c: len(json.load(open(os.path.join(ROOT, 'pkg/data', c + '.json')))['ops']) for c in cases}
        cases = [c for c in cases if nops[c] <= a.max_ops]
    jobs = []
    for p in a.problems:
        for c in sorted(cases, key=lambda c: -size[c]):
            for k in a.cores:
                cs = cand.get((p, c, k))
                if cs:
                    jobs.append((p, c, k, min(cs, key=lambda x: x['makespan']), OUTD, WIDTHS))
    print(f'成组合并作业 {len(jobs)} 个（每个至多 21 候选 + 基线），并行 {a.j}', flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=a.j) as ex:
        futs = {ex.submit(job, j): j for j in jobs}
        failed = []
        for f in as_completed(futs):
            done += 1
            try:
                f.result()
            except Exception as exc:                     # 子任务异常不能静默计为完成
                failed.append((futs[f][1], futs[f][2], futs[f][0], f'{type(exc).__name__}: {exc}'))
            if done % 50 == 0:
                print(f'  进度 {done}/{len(jobs)}  {time.strftime("%H:%M:%S")}', flush=True)
    missing = [j for j in jobs if not os.path.exists(os.path.join(OUTD, f'{j[1]}_k{j[2]}_p{j[0]}.json'))]
    print(f'==== 成组合并结束：预期 {len(jobs)}，落盘缺失 {len(missing)}，异常 {len(failed)} ====', flush=True)
    for x in failed[:10]:
        print('  异常', x, flush=True)
