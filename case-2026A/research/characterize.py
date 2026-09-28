# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""静态刻画每个计算图：算力、通信下界、关键路径，估算多核加速比上界。

不调用评估器，纯图分析，用于判断 A 题还有多少优化空间。
"""
import json, sys, os, collections
from concurrent.futures import ProcessPoolExecutor

EXCLUDED = {'COPY_IN', 'COPY_OUT'}
BW = 60  # bytes/cycle, 来自 config.txt


def op_dag(g):
    """把 tensor 中转边收缩成 op->op 依赖（保留 COPY 节点本身）。"""
    ops = {o['id']: o for o in g['ops']}
    succ = collections.defaultdict(set)
    pred = collections.defaultdict(set)
    producers = collections.defaultdict(set)
    consumers = collections.defaultdict(set)
    for e in g['edges']:
        s, t = e['source'], e['target']
        s_op, t_op = s in ops, t in ops
        if s_op and t_op and s != t:
            succ[s].add(t); pred[t].add(s)
        elif s_op and not t_op:
            producers[t].add(s)
        elif not s_op and t_op:
            consumers[s].add(t)
    for tid, prods in producers.items():
        for a in prods:
            for b in consumers.get(tid, ()):
                if a != b:
                    succ[a].add(b); pred[b].add(a)
    return ops, pred, succ, producers, consumers


def critical_path(ops, pred, succ):
    """最长路径（按 cycles 加权，COPY 节点权重 0）。"""
    indeg = {i: len(pred[i]) for i in ops}
    ready = [i for i in ops if indeg[i] == 0]
    order = []
    while ready:
        i = ready.pop()
        order.append(i)
        for j in succ[i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                ready.append(j)
    dist = {i: 0 for i in ops}
    for i in order:
        w = ops[i].get('cycles', 0) or 0
        d = dist[i] + w
        for j in succ[i]:
            if d > dist[j]:
                dist[j] = d
    return max((dist[i] + (ops[i].get('cycles', 0) or 0)) for i in ops) if ops else 0


def analyze(path):
    g = json.load(open(path))
    ops, pred, succ, producers, consumers = op_dag(g)
    tsize = {t['id']: t['size'] for t in g['tensors']}
    tpos = {t['id']: t['pos'] for t in g['tensors']}

    elig = [o for o in g['ops'] if o['op'] not in EXCLUDED]
    cyc = collections.Counter()
    for o in elig:
        cyc[o['pipe']] += o.get('cycles', 0) or 0

    # 强制 DDR 流量：图输入按"被多少个消费者读"暂记一次，图输出写一次
    ddr_in = sum(tsize[t] for t, p in tpos.items() if p == 'DDR' and t in consumers and t not in producers)
    ddr_out = sum(tsize[t] for t, p in tpos.items() if p == 'DDR' and t in producers)
    mand = ddr_in + ddr_out
    # 中间张量总量（切图切到就要付 2x）
    mid = sum(s for t, s in tsize.items() if tpos[t] != 'DDR')

    cp = critical_path(ops, pred, succ)
    return {
        'case': os.path.basename(path).replace('.json', ''),
        'n_ops': len(elig), 'n_all_ops': len(g['ops']), 'n_tensors': len(g['tensors']),
        'cyc_M': cyc.get('PIPE_M', 0), 'cyc_V': cyc.get('PIPE_V', 0),
        'cyc_total': sum(cyc.values()),
        'ddr_mandatory': mand, 'mid_bytes': mid,
        'ddr_lb_cycles': mand / BW,
        'crit_path': cp,
    }


if __name__ == '__main__':
    files = sorted(sys.argv[1:])
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(analyze, files))
    json.dump(rows, open(os.path.join(os.path.dirname(__file__), '..', 'runs', 'characterize.json'), 'w'), indent=1)

    print(f"{'case':10} {'ops':>7} {'cycM':>9} {'cycV':>9} {'critpath':>9} "
          f"{'mandDDR_cyc':>11} {'midMB':>7}  {'LB1':>9}")
    tot = collections.Counter()
    for r in rows:
        lb1 = max(r['cyc_M'], r['cyc_V'], r['ddr_lb_cycles'], r['crit_path'])
        tot['ops'] += r['n_ops']
        print(f"{r['case']:10} {r['n_ops']:7d} {r['cyc_M']:9d} {r['cyc_V']:9d} "
              f"{r['crit_path']:9d} {r['ddr_lb_cycles']:11.0f} {r['mid_bytes']/1e6:7.2f} {lb1:9.0f}")
    print(f"\n总 eligible ops: {tot['ops']}")
