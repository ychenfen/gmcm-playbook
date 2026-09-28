# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""B3：链收缩 + 通信感知表调度 + 递增 id 子图构造。

1. 极大链收缩：outdeg(i)==1 且 indeg(succ)==1 时合并，把长链压成超节点。
   （出度分布显示 98% 节点出度为 1，收缩后图规模常降一到两个数量级。）
2. 在收缩图上做表调度：按拓扑序，把超节点放到"最早完成"的核，
   跨核前驱按张量字节数折算通信代价。
3. 子图构造用递增 id 规则：节点 n 只能加入当前开放子图 S，当且仅当 n 的
   所有前驱都在 id < id(S) 的子图或 S 内；否则关闭 S、开一个新 id。
   于是子图间的边永远从小 id 指向大 id -> 商图无环，且每核按 id 升序
   排列即自动满足同核依赖顺序。
"""
import collections, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from algos import load_dag

BW = 60.0


def contract_chains(elig, cpred, csucc):
    """极大链收缩，返回 super_of[node] 与每个超节点的成员列表。"""
    super_of = {}
    members = []
    visited = set()
    for s in elig:
        if s in visited:
            continue
        # 只从"链头"起步：入度!=1 或 唯一前驱的出度!=1
        p = list(cpred[s])
        if len(p) == 1 and len(csucc[p[0]]) == 1:
            continue
        chain, cur = [], s
        while True:
            chain.append(cur); visited.add(cur)
            nx = list(csucc[cur])
            if len(nx) == 1 and len(cpred[nx[0]]) == 1 and nx[0] not in visited:
                cur = nx[0]
            else:
                break
        sid = len(members); members.append(chain)
        for n in chain:
            super_of[n] = sid
    for s in elig:                      # 兜底：环状残留自成一节点
        if s not in visited:
            sid = len(members); members.append([s])
            super_of[s] = sid; visited.add(s)
    return super_of, members


def build_plan_listsched(g, k, comm_weight=1.0):
    elig, cpred, csucc, info = load_dag(g)
    if not elig:
        return {'node_to_subgraph': {}, 'core_schedules': [[] for _ in range(k)]}
    tsize = {t['id']: t['size'] for t in g['tensors']}
    # op -> 其输出张量总字节（跨核时的通信代价近似）
    outbytes = collections.Counter()
    ops = {o['id'] for o in g['ops']}
    for e in g['edges']:
        if e['source'] in ops and e['target'] not in ops:
            outbytes[e['source']] += tsize.get(e['target'], 0)

    super_of, members = contract_chains(elig, cpred, csucc)
    S = len(members)
    spred = [set() for _ in range(S)]
    ssucc = [set() for _ in range(S)]
    for a in elig:
        sa = super_of[a]
        for b in csucc[a]:
            sb = super_of[b]
            if sa != sb:
                ssucc[sa].add(sb); spred[sb].add(sa)

    sw = []                                        # (wM, wV, out_bytes)
    for nl in members:
        m = v = ob = 0
        for i in nl:
            p, c = info[i]
            if p == 'PIPE_M': m += c
            elif p == 'PIPE_V': v += c
            ob += outbytes.get(i, 0)
        sw.append((m, v, ob))

    indeg = [len(spred[i]) for i in range(S)]
    q = collections.deque(sorted(i for i in range(S) if indeg[i] == 0))
    topo = []
    while q:
        i = q.popleft(); topo.append(i)
        for j in sorted(ssucc[i]):
            indeg[j] -= 1
            if indeg[j] == 0:
                q.append(j)

    # 表调度：核的两条流水各自累计，跨核前驱加通信延迟
    core_free = [0.0] * k
    finish = [0.0] * S
    core_of = [0] * S
    for n in topo:
        m, v, ob = sw[n]
        dur = max(m, v) if (m and v) else (m + v)
        best, bestfin = 0, None
        for c in range(k):
            ready = core_free[c]
            for p in spred[n]:
                t = finish[p] + (comm_weight * sw[p][2] / BW if core_of[p] != c else 0.0)
                if t > ready: ready = t
            fin = ready + dur
            if bestfin is None or fin < bestfin:
                best, bestfin = c, fin
        core_of[n] = best
        core_free[best] = bestfin
        finish[n] = bestfin

    # 递增 id 子图构造
    sg_of_super = [-1] * S
    open_sg = [-1] * k
    sg_count = 0
    core_sched = [[] for _ in range(k)]
    for n in topo:
        c = core_of[n]
        ok = open_sg[c] >= 0 and all(
            sg_of_super[p] < open_sg[c] or sg_of_super[p] == open_sg[c]
            for p in spred[n])
        if not ok:
            open_sg[c] = sg_count; sg_count += 1
            core_sched[c].append(open_sg[c])
        sg_of_super[n] = open_sg[c]

    node_to_sg = {}
    for sid, nl in enumerate(members):
        g_id = sg_of_super[sid]
        for i in nl:
            node_to_sg[str(i)] = g_id
    return {'node_to_subgraph': node_to_sg, 'core_schedules': core_sched}
