# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具名称：Claude Code；版本/型号：Claude Opus 5.5；开发机构：Anthropic；版本颁布日期：2026 年 9 月 22 日
# 算法 1：分量装箱与拓扑区间切分。
# 每个子图都是全局拓扑序中的一段连续区间，所以商图无环；同核子图按区间起点排序即满足依赖。
import collections

# 官方材料包的 code/ 目录由 solve.py 加入 sys.path
from stub_multicore_cut_and_schedule import _build_op_adjacency, _contract_excluded_copy_nodes

EXCLUDED = {'COPY_IN', 'COPY_OUT'}


def load_dag(g):
    # 可分配操作、跨过 COPY 节点收缩后的前驱/后继表、每个操作的 (流水线, 周期)
    elig = sorted(o['id'] for o in g['ops'] if o['op'] not in EXCLUDED)
    _, succs = _build_op_adjacency(g)
    cpred, csucc = _contract_excluded_copy_nodes(elig, succs)
    info = {o['id']: (o['pipe'], o.get('cycles') or 0) for o in g['ops']}
    return elig, cpred, csucc, info


def components(elig, csucc, cpred):
    # 并查集求弱连通分量
    par = {i: i for i in elig}

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    for a in elig:
        for b in csucc[a]:
            ra, rb = find(a), find(b)
            if ra != rb:
                par[ra] = rb
    comp = collections.defaultdict(list)
    for i in elig:
        comp[find(i)].append(i)
    return list(comp.values())


def dfs_topo(nodes, cpred, csucc):
    # 深度优先的拓扑序：沿生产者-消费者链往下走，相邻操作尽量排在一起，切区间时少切断依赖
    nodeset = set(nodes)
    indeg = {i: sum(1 for p in cpred[i] if p in nodeset) for i in nodes}
    stack = list(reversed(sorted(i for i in nodes if indeg[i] == 0)))
    order, seen = [], set()
    while stack:
        i = stack.pop()
        if i in seen or indeg[i] > 0:
            continue
        seen.add(i)
        order.append(i)
        nxt = []
        for j in sorted(csucc[i]):
            if j not in nodeset or j in seen:
                continue
            indeg[j] -= 1
            if indeg[j] == 0:
                nxt.append(j)
        stack.extend(reversed(nxt))
    if len(order) != len(nodes):
        # 正常不会走到这里；万一有遗漏，用 Kahn 算法补齐
        rest = [i for i in nodes if i not in seen]
        indeg = {i: sum(1 for p in cpred[i] if p in nodeset and p not in seen) for i in rest}
        q = sorted(i for i in rest if indeg[i] == 0)
        while q:
            i = q.pop(0)
            order.append(i)
            seen.add(i)
            for j in sorted(csucc[i]):
                if j in nodeset and j not in seen:
                    indeg[j] -= 1
                    if indeg[j] == 0:
                        q.append(j)
                        q.sort()
    return order


def _w(nodes, info):
    # 一组操作的 Cube、Vector 周期和
    m = v = 0
    for i in nodes:
        p, c = info[i]
        if p == 'PIPE_M':
            m += c
        elif p == 'PIPE_V':
            v += c
    return m, v


def build_plan_lpt(g, k, chunk_div=2.0):
    # chunk_div 即论文中的 alpha，区间上限 w_bar = max(W_M, W_V) / (k * alpha)
    elig, cpred, csucc, info = load_dag(g)
    if not elig:
        return {'node_to_subgraph': {}, 'core_schedules': [[] for _ in range(k)]}

    comps = components(elig, csucc, cpred)
    comp_orders = [dfs_topo(c, cpred, csucc) for c in comps]
    comp_orders.sort(key=lambda o: o[0])          # 分量之间没有依赖，按首元素拼接即为全局拓扑序

    tot_m, tot_v = _w(elig, info)
    target = max(tot_m, tot_v) / k if k else 0
    cap = max(target / chunk_div, 1.0)

    chunks, rank = [], 0                          # (区间起点在全局序中的位置, 操作列表)
    for order in comp_orders:
        cm, cv = _w(order, info)
        if max(cm, cv) <= cap:
            chunks.append((rank, order))
            rank += len(order)
            continue
        cur, curm, curv = [], 0, 0
        for i in order:
            p, c = info[i]
            nm = curm + (c if p == 'PIPE_M' else 0)
            nv = curv + (c if p == 'PIPE_V' else 0)
            if cur and max(nm, nv) > cap:
                chunks.append((rank, cur))
                rank += len(cur)
                cur = []
                nm = c if p == 'PIPE_M' else 0
                nv = c if p == 'PIPE_V' else 0
            cur.append(i)
            curm, curv = nm, nv
        if cur:
            chunks.append((rank, cur))
            rank += len(cur)

    # LPT：区间按 max(wM, wV) 降序，放到放入后 max(Cube 负载, Vector 负载) 最小的核
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
        loads[best][0] += wm
        loads[best][1] += wv
        assign[best].append((r, nodes))

    node_to_sg, core_sched, sg = {}, [], 0
    for c in range(k):
        assign[c].sort(key=lambda x: x[0])        # 同核按区间起点排序
        core_sched.append([])
        for r, nodes in assign[c]:
            for i in nodes:
                node_to_sg[str(i)] = sg
            core_sched[c].append(sg)
            sg += 1
    return {'node_to_subgraph': node_to_sg, 'core_schedules': core_sched}
