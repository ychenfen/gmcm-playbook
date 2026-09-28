# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""B2：层带 × 核 分区。

核心思路：按最长路径层级把 DAG 切成 W 个层带，带内节点近乎互相独立，
可自由分配到不同核实现并行；带间天然单向依赖。

无环性保证：带内先把有直接边相连的节点并成"原子组"（同组必同核），
因此带内不存在跨核依赖；带间边只从低带指向高带。商图必然无环。
"""
import collections, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from algos import load_dag


def levels(elig, cpred, csucc):
    """按边数计的最长路径层级（保证 level[j] > level[i] 对每条 i->j）。"""
    indeg = {i: len(cpred[i]) for i in elig}
    q = collections.deque(i for i in elig if indeg[i] == 0)
    order = []
    while q:
        i = q.popleft(); order.append(i)
        for j in csucc[i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                q.append(j)
    lv = {i: 0 for i in elig}
    for i in order:
        for j in csucc[i]:
            if lv[i] + 1 > lv[j]:
                lv[j] = lv[i] + 1
    return lv, order


def build_plan_band(g, k, n_bands=8):
    elig, cpred, csucc, info = load_dag(g)
    if not elig:
        return {'node_to_subgraph': {}, 'core_schedules': [[] for _ in range(k)]}
    lv, topo = levels(elig, cpred, csucc)

    # 按累计算力把层级切成 n_bands 个带，使每带算力大致相等
    by_lv = collections.defaultdict(list)
    for i in elig:
        by_lv[lv[i]].append(i)
    lv_keys = sorted(by_lv)
    lv_w = {L: sum(info[i][1] for i in by_lv[L]) for L in lv_keys}
    total = sum(lv_w.values()) or 1
    per = total / max(n_bands, 1)
    band_of_lv, b, acc = {}, 0, 0.0
    for L in lv_keys:
        band_of_lv[L] = b
        acc += lv_w[L]
        if acc >= per * (b + 1) and b < n_bands - 1:
            b += 1
    bands = collections.defaultdict(list)
    for i in elig:
        bands[band_of_lv[lv[i]]].append(i)

    node_to_sg, core_sched, sg = {}, [[] for _ in range(k)], 0
    for b in sorted(bands):
        nodes = bands[b]
        nset = set(nodes)
        # 带内原子组：有直接边相连的节点必须同核（否则带内会出现跨核依赖）
        par = {i: i for i in nodes}
        def find(x):
            while par[x] != x:
                par[x] = par[par[x]]; x = par[x]
            return x
        for a in nodes:
            for c in csucc[a]:
                if c in nset:
                    ra, rb = find(a), find(c)
                    if ra != rb: par[ra] = rb
        grp = collections.defaultdict(list)
        for i in nodes:
            grp[find(i)].append(i)

        gw = []
        for nl in grp.values():
            m = v = 0
            for i in nl:
                p, c = info[i]
                if p == 'PIPE_M': m += c
                elif p == 'PIPE_V': v += c
            gw.append((max(m, v), m, v, sorted(nl)))
        gw.sort(key=lambda x: -x[0])

        loads = [[0, 0] for _ in range(k)]
        buckets = [[] for _ in range(k)]
        for _, m, v, nl in gw:
            best, bc = 0, None
            for c in range(k):
                cost = max(loads[c][0] + m, loads[c][1] + v)
                if bc is None or cost < bc:
                    best, bc = c, cost
            loads[best][0] += m; loads[best][1] += v
            buckets[best].extend(nl)
        for c in range(k):
            if not buckets[c]:
                continue
            for i in buckets[c]:
                node_to_sg[str(i)] = sg
            core_sched[c].append(sg)
            sg += 1
    return {'node_to_subgraph': node_to_sg, 'core_schedules': core_sched}
