# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""只对“当前最优候选来自补充参数网格”的 (问题, 用例, 核数) 做成组合并，输出 runs/co3/（与 runs/co 同格式，finalize 自动纳入）。

补充网格：层带划分 W∈{32,64,128,512,1024}，相位构造 λ∈{500,1000,5000,20000,100000}（仅单一巨块与主块加碎片两族）。
"""
import os, sys, argparse, time
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coarsen
from finalize import load_candidates, ROOT

DENSE = {'band': {32.0, 64.0, 128.0, 512.0, 1024.0}, 'phase': {500.0, 1000.0, 5000.0, 20000.0, 100000.0}}

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('-j', type=int, default=6); ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    outd = os.path.join(ROOT, 'runs', 'co3'); os.makedirs(os.path.join(outd, 'plans'), exist_ok=True)
    cand = load_candidates()
    jobs = []
    for (p, c, k), cs in cand.items():
        if k < 2 and p != 3:
            continue
        b = min(cs, key=lambda x: x['makespan'])
        if b.get('src') == 'sweep' and float(b.get('div', -1)) in DENSE.get(b.get('algo'), ()):
            jobs.append((p, c, k, b, outd, coarsen.WIDTHS))
    size = {j[1]: os.path.getsize(os.path.join(ROOT, 'pkg', 'data', j[1] + '.json')) for j in jobs}
    jobs.sort(key=lambda j: size[j[1]])
    print(f'补充网格胜出组的成组合并：{len(jobs)} 组', flush=True)
    if a.dry_run:
        sys.exit(0)
    fail = []
    with ProcessPoolExecutor(max_workers=a.j) as ex:
        futs = {ex.submit(coarsen.job, j): j for j in jobs}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                f.result()
            except Exception as e:
                fail.append((futs[f][:3], repr(e)))
            if i % 20 == 0:
                print(f'  进度 {i}/{len(jobs)} {time.strftime("%H:%M:%S")}', flush=True)
    miss = [j for j in jobs if not os.path.exists(os.path.join(outd, f'{j[1]}_k{j[2]}_p{j[0]}.json'))]
    print(f'==== 成组合并（补充网格）结束：{len(jobs)} 组，缺失 {len(miss)}，异常 {len(fail)} ====', flush=True)
    for x in fail[:10]:
        print('  异常', x, flush=True)
