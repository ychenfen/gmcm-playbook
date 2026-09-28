# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""B4：通信感知表调度（op 级） + 相位构造子图。

两段式：
(1) 在 op 级做表调度，得到 op -> 核 的分配。跨核前驱按张量字节/带宽 + 固定
    同步延迟计代价，因此小图会自动倾向于少切跨核边。
(2) 相位构造：phase(v) = max over preds u of (phase(u) + [core(u) != core(v)])。
    子图 = (核, 相位)。每条跨核边都严格抬高相位，故按相位排序的商图必然无环；
    同核边不抬相位，于是同核连续计算自然聚成一个子图，子图数被压到最小。

关键：子图数 = 各核用到的相位数之和，只由"路径上的换核次数"决定。
调度阶段的 sync_penalty 直接压这个量。
"""
import collections, sys, os, heapq
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from algos import load_dag

BW = 60.0


def build_plan_phase(g, k, comm_weight=1.0, sync_penalty=500.0, lookahead=True, cache_bw=None):
    """cache_bw 不为 None 时启用缓存感知代价（问题3）：张量已被某个核从 DDR 读过后，
    其他核再读按缓存带宽 cache_bw 计价，而不是 DDR 带宽。这降低了跨核扇出的代价，
    让调度器在有共享只读缓存时敢于把同一张量的消费者分到多个核上。"""
    elig, cpred, csucc, info = load_dag(g)
    if not elig:
        return {'node_to_subgraph': {}, 'core_schedules': [[] for _ in range(k)]}
    tsize = {t['id']: t['size'] for t in g['tensors']}
    ops = {o['id'] for o in g['ops']}
    outbytes = collections.Counter()
    for e in g['edges']:
        if e['source'] in ops and e['target'] not in ops:
            outbytes[e['source']] += tsize.get(e['target'], 0)

    # 反向关键路径（bottom level），用作表调度优先级
    indeg = {i: len(cpred[i]) for i in elig}
    q = collections.deque(i for i in elig if indeg[i] == 0)
    topo = []
    while q:
        i = q.popleft(); topo.append(i)
        for j in csucc[i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                q.append(j)
    blevel = {i: 0 for i in elig}
    for i in reversed(topo):
        b = 0
        for j in csucc[i]:
            if blevel[j] > b: b = blevel[j]
        blevel[i] = b + info[i][1]

    # 表调度：就绪队列按 blevel 降序；每核按流水线分别累计占用
    pipes = ('PIPE_M', 'PIPE_V', 'PIPE_MTE2', 'PIPE_MTE3')
    avail = {(c, p): 0.0 for c in range(k) for p in pipes}
    core_of, finish = {}, {}
    imported = collections.defaultdict(set)     # u -> 已从 DDR 读过 u 输出的核
    rem = {i: len(cpred[i]) for i in elig}
    ready = [(-blevel[i], i) for i in elig if rem[i] == 0]
    heapq.heapify(ready)
    while ready:
        _, v = heapq.heappop(ready)
        p, cyc = info[v]
        best, bfin = 0, None
        for c in range(k):
            est = avail[(c, p)]
            for u in cpred[v]:
                t = finish[u]
                if core_of[u] != c:
                    if cache_bw and imported[u] and c not in imported[u]:
                        bw = cache_bw                      # 已有别的核读过 → 大概率缓存命中
                    else:
                        bw = BW
                    t += sync_penalty + comm_weight * outbytes.get(u, 0) / bw
                if t > est: est = t
            fin = est + cyc
            if bfin is None or fin < bfin:
                best, bfin = c, fin
        core_of[v] = best; finish[v] = bfin; avail[(best, p)] = bfin
        for u in cpred[v]:
            if core_of[u] != best:
                imported[u].add(best)
        for w in csucc[v]:
            rem[w] -= 1
            if rem[w] == 0:
                heapq.heappush(ready, (-blevel[w], w))

    # 相位构造
    phase = {}
    for v in topo:
        ph = 0
        for u in cpred[v]:
            cand = phase[u] + (1 if core_of[u] != core_of[v] else 0)
            if cand > ph: ph = cand
        phase[v] = ph

    key_to_sg, node_to_sg = {}, {}
    per_core = collections.defaultdict(list)
    for v in elig:
        key = (phase[v], core_of[v])
        if key not in key_to_sg:
            key_to_sg[key] = len(key_to_sg)
        node_to_sg[str(v)] = key_to_sg[key]
    for (ph, c), sid in key_to_sg.items():
        per_core[c].append((ph, sid))
    core_sched = []
    for c in range(k):
        core_sched.append([sid for _, sid in sorted(per_core[c])])
    return {'node_to_subgraph': node_to_sg, 'core_schedules': core_sched}
