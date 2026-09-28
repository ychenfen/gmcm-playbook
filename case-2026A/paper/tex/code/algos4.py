# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具名称：Claude Code；版本/型号：Claude Opus 5.5；开发机构：Anthropic；版本颁布日期：2026 年 9 月 22 日
# 算法 3：通信感知表调度与相位构造。
# 第一步在操作粒度上做表调度，决定每个操作的核心；跨核前驱额外计 sync_penalty（论文中的 lambda）
# 与张量传输时间。第二步按 phase(v) = max_u {phase(u) + [core(u) != core(v)]} 计算相位，
# (核, 相位) 相同的操作组成一个子图。跨核边使相位严格增加，所以商图无环。
import collections
import heapq
from .algos import load_dag

BW = 60.0          # DDR 带宽，bytes/cycle


def build_plan_phase(g, k, comm_weight=1.0, sync_penalty=500.0, cache_bw=None):
    # cache_bw 用于问题三的缓存感知变体（论文中未采用的路线）：某张量已被别的核读过时，
    # 再次跨核读取按缓存带宽计价。正式结果使用 cache_bw=None。
    elig, cpred, csucc, info = load_dag(g)
    if not elig:
        return {'node_to_subgraph': {}, 'core_schedules': [[] for _ in range(k)]}
    tsize = {t['id']: t['size'] for t in g['tensors']}
    ops = {o['id'] for o in g['ops']}
    outbytes = collections.Counter()               # 每个操作输出张量的字节数
    for e in g['edges']:
        if e['source'] in ops and e['target'] not in ops:
            outbytes[e['source']] += tsize.get(e['target'], 0)

    # 拓扑序与自底向上关键路径长度 bl(v)
    indeg = {i: len(cpred[i]) for i in elig}
    q = collections.deque(i for i in elig if indeg[i] == 0)
    topo = []
    while q:
        i = q.popleft()
        topo.append(i)
        for j in csucc[i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                q.append(j)
    blevel = {i: 0 for i in elig}
    for i in reversed(topo):
        b = 0
        for j in csucc[i]:
            if blevel[j] > b:
                b = blevel[j]
        blevel[i] = b + info[i][1]

    # 表调度：就绪操作按 bl 降序取出，放到估计完成时刻 F(v, n) 最小的核
    pipes = ('PIPE_M', 'PIPE_V', 'PIPE_MTE2', 'PIPE_MTE3')
    avail = {(c, p): 0.0 for c in range(k) for p in pipes}
    core_of, finish = {}, {}
    imported = collections.defaultdict(set)        # 操作 u 的输出已被哪些核读入
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
                    bw = cache_bw if (cache_bw and imported[u] and c not in imported[u]) else BW
                    t += sync_penalty + comm_weight * outbytes.get(u, 0) / bw
                if t > est:
                    est = t
            fin = est + cyc
            if bfin is None or fin < bfin:
                best, bfin = c, fin
        core_of[v] = best
        finish[v] = bfin
        avail[(best, p)] = bfin
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
            if cand > ph:
                ph = cand
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
    core_sched = [[sid for _, sid in sorted(per_core[c])] for c in range(k)]
    return {'node_to_subgraph': node_to_sg, 'core_schedules': core_sched}
