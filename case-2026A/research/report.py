# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""汇总：单核基准 vs 多核方案，出加速比曲线与到理论下界的差距。"""
import json, os, re, glob, statistics, collections, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def singlecore():
    ms = {}
    for f in glob.glob(os.path.join(ROOT, 'runs', 'singlecore', 'case_*.log')):
        c = os.path.basename(f).replace('.log', '')
        m = re.search(r'makespan=([\d,]+)', open(f).read())
        if m:
            ms[c] = int(m.group(1).replace(',', ''))
    return ms


def lb(r, n):
    return max(r['crit_path'], r['cyc_M'] / n, r['cyc_V'] / n, r['ddr_lb_cycles'])


if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else 'runs/full_p1_lpt.json'
    rows = json.load(open(os.path.join(ROOT, src)))
    char = {r['case']: r for r in json.load(open(os.path.join(ROOT, 'runs', 'characterize.json')))}
    sc = singlecore()
    by = collections.defaultdict(dict)
    for r in rows:
        if 'err' not in r:
            by[r['case']][r['k']] = r

    cores = sorted({r['k'] for r in rows if 'err' not in r})
    print(f"缺单核基准的用例: {sorted(set(by) - set(sc))}\n")
    usable = [c for c in sorted(by) if c in sc]
    print(f"可用用例 {len(usable)}/100\n")

    print(f"{'核数':>4} {'加速比均值':>10} {'中位':>8} {'最差':>8} {'最好':>8} "
          f"{'理论上界均值':>12} {'达成率':>8} {'额外流量倍数':>12}")
    summary = {}
    for k in cores:
        sp, ceil, tr = [], [], []
        for c in usable:
            if k not in by[c]:
                continue
            r = by[c][k]
            sp.append(sc[c] / r['makespan'])
            ceil.append(sc[c] / lb(char[c], k))
            if r.get('orig_bytes'):
                tr.append(r['sched_bytes'] / r['orig_bytes'])
        ach = statistics.mean(s / cl for s, cl in zip(sp, ceil))
        summary[k] = (statistics.mean(sp), statistics.mean(ceil), ach)
        print(f"{k:>4} {statistics.mean(sp):>10.2f} {statistics.median(sp):>8.2f} "
              f"{min(sp):>8.2f} {max(sp):>8.2f} {statistics.mean(ceil):>12.2f} "
              f"{ach*100:>7.1f}% {statistics.mean(tr):>12.2f}x")

    print("\n—— 单调性检查：加速比随核数是否单增 ——")
    bad = []
    for c in usable:
        seq = [sc[c] / by[c][k]['makespan'] for k in cores if k in by[c]]
        if any(seq[i+1] < seq[i] - 1e-9 for i in range(len(seq)-1)):
            bad.append((c, [round(x, 2) for x in seq]))
    print(f"非单增用例: {len(bad)}/{len(usable)}")
    for c, s in bad[:12]:
        print(f"  {c}: {s}")

    print("\n—— 距离理论下界最远的 15 个用例 (k=4) ——")
    gaps = []
    for c in usable:
        if 4 in by[c]:
            g = by[c][4]['makespan'] / lb(char[c], 4)
            gaps.append((g, c, by[c][4]))
    gaps.sort(reverse=True)
    print(f"{'case':10} {'gap':>6} {'makespan':>12} {'LB(4)':>12} {'子图数':>7} "
          f"{'流量倍数':>9} {'spill':>12} {'taskdeps':>9}")
    for g, c, r in gaps[:15]:
        print(f"{c:10} {g:6.2f} {r['makespan']:>12,} {lb(char[c],4):>12,.0f} "
              f"{r['n_subgraphs']:>7} {(r['sched_bytes']/r['orig_bytes'] if r.get('orig_bytes') else 0):>9.2f} "
              f"{(r.get('spill_bytes') or 0)/1e6:>10.1f}MB {r.get('n_task_deps',0):>9}")
    print(f"\ngap 中位={statistics.median(g for g,_,_ in gaps):.2f}  "
          f"均值={statistics.mean(g for g,_,_ in gaps):.2f}")
