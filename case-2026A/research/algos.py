# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""多核切图与调度算法。

B0 = 官方 stub（随机），B1 = 连通分量 + DFS 拓扑区间切分 + LPT 双维装箱。

合法性依据：所有子图都是"某个全局拓扑序的连续区间"，因而商图必然无环；
每核内按区间起点的全局拓扑秩排序，自动满足同核依赖顺序约束。
"""
import json, collections, sys, os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pkg', 'code'))
from stub_multicore_cut_and_schedule import _build_op_adjacency, _contract_excluded_copy_nodes

EXCLUDED = {'COPY_IN', 'COPY_OUT'}


def load_dag(g):
    """返回 eligible op 上的收缩 DAG、每 op 的 (pipe, cycles)。"""
    elig = sorted(o['id'] for o in g['ops'] if o['op'] not in EXCLUDED)
    _, succs = _build_op_adjacency(g)
    cpred, csucc = _contract_excluded_copy_nodes(elig, succs)
    info = {o['id']: (o['pipe'], o.get('cycles') or 0) for o in g['ops']}
    return elig, cpred, csucc, info


def components(elig, csucc, cpred):
    par = {i: i for i in elig}
    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    for a in elig:
        for b in csucc[a]:
            ra, rb = find(a), find(b)
            if ra != rb: par[ra] = rb
    comp = collections.defaultdict(list)
    for i in elig:
        comp[find(i)].append(i)
    return list(comp.values())


def dfs_topo(nodes, cpred, csucc):
    """DFS 风格拓扑序：优先跟着生产者-消费者链走，让区间切分少切边。"""
    nodeset = set(nodes)
    indeg = {i: sum(1 for p in cpred[i] if p in nodeset) for i in nodes}
    ready = sorted(i for i in nodes if indeg[i] == 0)
    stack = list(reversed(ready))
    order, seen = [], set()
    while stack:
        i = stack.pop()
        if i in seen or indeg[i] > 0:
            continue
        seen.add(i); order.append(i)
        nxt = []
        for j in sorted(csucc[i]):
            if j not in nodeset or j in seen:
                continue
            indeg[j] -= 1
            if indeg[j] == 0:
                nxt.append(j)
        stack.extend(reversed(nxt))
    if len(order) != len(nodes):   # 兜底：Kahn 补齐
        rest = [i for i in nodes if i not in seen]
        indeg = {i: sum(1 for p in cpred[i] if p in nodeset and p not in seen) for i in rest}
        q = sorted(i for i in rest if indeg[i] == 0)
        while q:
            i = q.pop(0); order.append(i); seen.add(i)
            for j in sorted(csucc[i]):
                if j in nodeset and j not in seen:
                    indeg[j] -= 1
                    if indeg[j] == 0:
                        q.append(j); q.sort()
    return order


def _w(nodes, info):
    m = v = 0
    for i in nodes:
        p, c = info[i]
        if p == 'PIPE_M': m += c
        elif p == 'PIPE_V': v += c
    return m, v


def build_plan_lpt(g, k, chunk_div=2.0):
    elig, cpred, csucc, info = load_dag(g)
    if not elig:
        return {'node_to_subgraph': {}, 'core_schedules': [[] for _ in range(k)]}

    comps = components(elig, csucc, cpred)
    # 全局拓扑序 = 各分量 DFS 拓扑序依次拼接（分量间无依赖，拼接合法）
    comp_orders = [dfs_topo(c, cpred, csucc) for c in comps]
    comp_orders.sort(key=lambda o: o[0])

    tot_m, tot_v = _w(elig, info)
    target = max(tot_m, tot_v) / k if k else 0
    cap = max(target / chunk_div, 1.0)

    chunks, rank = [], 0
    for order in comp_orders:
        cm, cv = _w(order, info)
        if max(cm, cv) <= cap:
            chunks.append((rank, order)); rank += len(order)
            continue
        cur, curm, curv = [], 0, 0
        for i in order:
            p, c = info[i]
            nm = curm + (c if p == 'PIPE_M' else 0)
            nv = curv + (c if p == 'PIPE_V' else 0)
            if cur and max(nm, nv) > cap:
                chunks.append((rank, cur)); rank += len(cur)
                cur, curm, curv = [], 0, 0
                nm = c if p == 'PIPE_M' else 0
                nv = c if p == 'PIPE_V' else 0
            cur.append(i); curm, curv = nm, nv
        if cur:
            chunks.append((rank, cur)); rank += len(cur)

    # LPT 双维装箱：按 max(wM,wV) 降序，放到"放完之后核负载最小"的核
    weighted = [(r, nodes) + _w(nodes, info) for r, nodes in chunks]
    weighted.sort(key=lambda x: -max(x[2], x[3]))
    loads = [[0, 0] for _ in range(k)]
    assign = [[] for _ in range(k)]
    for r, nodes, wm, wv in weighted:
        best, bestcost = 0, None
        for c in range(k):
            cost = max(loads[c][0] + wm, loads[c][1] + wv)
            if bestcost is None or cost < bestcost:
                best, bestcost = c, cost
        loads[best][0] += wm; loads[best][1] += wv
        assign[best].append((r, nodes))

    node_to_sg, core_sched, sg = {}, [], 0
    tagged = []
    for c in range(k):
        assign[c].sort(key=lambda x: x[0])          # 按全局拓扑秩，保证同核依赖顺序
        tagged.append([])
    for c in range(k):
        for r, nodes in assign[c]:
            for i in nodes:
                node_to_sg[str(i)] = sg
            tagged[c].append(sg); sg += 1
    core_sched = tagged
    return {'node_to_subgraph': node_to_sg, 'core_schedules': core_sched}
