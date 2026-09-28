# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""B5：最重边链聚类 + LPT 装箱 + 簇级相位构造。

动机：case_002 是 199 条并行链汇聚到 1 个汇点，理想切法是"每核拿 50 条整链"，
只在汇点切。层带法（横切）和相位法（op 级）都找不到它。

(1) 链聚类：按拓扑序，每个节点 v 挑通信量最大、且尚未被别的后继"接管"的前驱 u，
    并入 u 的簇；否则自成新簇。于是每个簇是一条沿重边的路径，被切开的只有轻边。
(2) LPT 双维装箱把簇分到核上。
(3) 簇级相位构造：phase(簇) = max over 前驱簇 (phase + [异核])，子图 = (核, 相位)。
    簇的数量远少于 op，相位数因而远小于 B4，子图不再碎。
"""
import collections, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from algos import load_dag


def _scc(n, adj):
    """Tarjan 强连通分量，返回 comp[i]；编号已按逆拓扑序压实。"""
    index = [0]
    idx, low, on, stack, comp = {}, {}, set(), [], [-1] * n
    cid = [0]
    for root in range(n):
        if root in idx:
            continue
        work = [(root, iter(sorted(adj[root])))]
        idx[root] = low[root] = index[0]; index[0] += 1
        stack.append(root); on.add(root)
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in idx:
                    idx[w] = low[w] = index[0]; index[0] += 1
                    stack.append(w); on.add(w)
                    work.append((w, iter(sorted(adj[w]))))
                    advanced = True
                    break
                if w in on and idx[w] < low[v]:
                    low[v] = idx[w]
            if advanced:
                continue
            work.pop()
            if low[v] == idx[v]:
                while True:
                    w = stack.pop(); on.discard(w); comp[w] = cid[0]
                    if w == v:
                        break
                cid[0] += 1
            if work:
                u = work[-1][0]
                if low[v] < low[u]:
                    low[u] = low[v]
    # Tarjan 给的是逆拓扑序，翻转成拓扑序（不影响正确性，只为可读）
    return [cid[0] - 1 - c for c in comp]


def build_plan_cluster(g, k, merge_ratio=1.0):
    elig, cpred, csucc, info = load_dag(g)
    if not elig:
        return {'node_to_subgraph': {}, 'core_schedules': [[] for _ in range(k)]}
    tsize = {t['id']: t['size'] for t in g['tensors']}
    ops = {o['id'] for o in g['ops']}
    outb = collections.Counter()
    for e in g['edges']:
        if e['source'] in ops and e['target'] not in ops:
            outb[e['source']] += tsize.get(e['target'], 0)

    indeg = {i: len(cpred[i]) for i in elig}
    q = collections.deque(sorted(i for i in elig if indeg[i] == 0))
    topo = []
    while q:
        i = q.popleft(); topo.append(i)
        for j in sorted(csucc[i]):
            indeg[j] -= 1
            if indeg[j] == 0:
                q.append(j)

    # (1) 最重边链聚类
    cluster = {}
    extended = set()          # 已被某个后继接管的簇
    members = collections.defaultdict(list)
    for v in topo:
        cand = [u for u in cpred[v] if cluster[u] not in extended]
        if cand:
            u = max(cand, key=lambda x: (outb.get(x, 0), -x))
            cid = cluster[u]
            extended.add(cid)
        else:
            cid = len(members)
        cluster[v] = cid
        members[cid].append(v)

    cids = sorted(members)
    remap = {c: i for i, c in enumerate(cids)}
    cluster = {v: remap[c] for v, c in cluster.items()}
    members = {remap[c]: members[c] for c in cids}
    C = len(members)

    # 链聚类会在簇图上造环（p2 选了 p1 当宿主，而 p1 另有后继落在 q2 的簇里，
    # 同时 q2 -> p2）。对簇图做 SCC 缩点，缩完的凝聚图必是 DAG。
    adj = [set() for _ in range(C)]
    for v in elig:
        a = cluster[v]
        for w in csucc[v]:
            b = cluster[w]
            if a != b:
                adj[a].add(b)
    comp = _scc(C, adj)
    if max(comp) + 1 != C:                       # 确实有环才重建
        newmem = collections.defaultdict(list)
        for c in range(C):
            newmem[comp[c]].extend(members[c])
        cluster = {v: comp[cluster[v]] for v in elig}
        members = dict(newmem)
        C = max(comp) + 1

    cpredc = [set() for _ in range(C)]
    csuccc = [set() for _ in range(C)]
    for v in elig:
        a = cluster[v]
        for w in csucc[v]:
            b = cluster[w]
            if a != b:
                csuccc[a].add(b); cpredc[b].add(a)

    cw = []
    for c in range(C):
        m = vv = 0
        for i in members[c]:
            p, cy = info[i]
            if p == 'PIPE_M': m += cy
            elif p == 'PIPE_V': vv += cy
        cw.append((m, vv))

    # (2) LPT 双维装箱
    order = sorted(range(C), key=lambda c: -max(cw[c]))
    loads = [[0, 0] for _ in range(k)]
    core_of = [0] * C
    for c in order:
        m, vv = cw[c]
        best, bc = 0, None
        for j in range(k):
            cost = max(loads[j][0] + m, loads[j][1] + vv)
            if bc is None or cost < bc:
                best, bc = j, cost
        core_of[c] = best
        loads[best][0] += m; loads[best][1] += vv

    # (3) 簇级相位构造
    ind = [len(cpredc[c]) for c in range(C)]
    qq = collections.deque(c for c in range(C) if ind[c] == 0)
    ctopo = []
    while qq:
        c = qq.popleft(); ctopo.append(c)
        for d in csuccc[c]:
            ind[d] -= 1
            if ind[d] == 0:
                qq.append(d)
    phase = [0] * C
    for c in ctopo:
        ph = 0
        for p in cpredc[c]:
            cand = phase[p] + (1 if core_of[p] != core_of[c] else 0)
            if cand > ph: ph = cand
        phase[c] = ph

    key_to_sg, per_core = {}, collections.defaultdict(list)
    node_to_sg = {}
    for c in range(C):
        key = (phase[c], core_of[c])
        if key not in key_to_sg:
            key_to_sg[key] = len(key_to_sg)
            per_core[core_of[c]].append((phase[c], key_to_sg[key]))
        for v in members[c]:
            node_to_sg[str(v)] = key_to_sg[key]
    core_sched = [[sid for _, sid in sorted(per_core[c])] for c in range(k)]
    return {'node_to_subgraph': node_to_sg, 'core_schedules': core_sched}
