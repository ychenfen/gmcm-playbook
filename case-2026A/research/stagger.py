# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""问题3 缓存感知后处理：错开共享张量的读取时机，把"并发缺失"变成缓存命中。

诊断（src/cache_diag.py --survey 4）：100 个用例里并发缺失平均占缓存访问字节的 11.4%——
多个核几乎同时对同一逻辑张量发起 COPY_IN，第一个还没完成写入缓存，其余全部未命中，
一起挤占 60 B/cycle 的 DDR。错开之后，只有领读核走 DDR，其余核走 250 B/cycle 的缓存。

做法（不改切图，只改各核内子图的先后顺序）：
1. 找出被 ≥2 个核读取的逻辑张量：
   - 图输入：原图 COPY_IN 的片上输出张量，其消费者分布在多个核上（评估器会按核复制 COPY_IN，逻辑 id 相同）；
   - 跨核中间张量：生产者在核 a，消费者分布在其他 ≥2 个核上。
2. 按张量大小从大到小为每个共享张量指定一个领读核（在读它的核里挑当前领读负担最小的）。
3. 子图得分 = Σ 领读张量大小 − Σ 跟读张量大小；领读的往前排，跟读的往后排。
4. 在全体子图的商图上做带优先级的 Kahn 拓扑排序，各核顺序取这个全局序的投影——
   这样得到的各核顺序与同一个全局拓扑序一致，跨核不会互相等待成环。
"""
import heapq, collections, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pkg', 'code'))
from stub_multicore_cut_and_schedule import derive_multicore_plan


def shared_tensors(g, plan):
    ops = {o['id']: o for o in g['ops']}
    tensors = {t['id']: t for t in g['tensors']}
    n2s = {int(k): v for k, v in plan['node_to_subgraph'].items()}
    core_of_sg = {sg: c for c, order in enumerate(plan['core_schedules']) for sg in order}
    prod, cons = collections.defaultdict(list), collections.defaultdict(list)
    for e in g['edges']:
        s, t = e['source'], e['target']
        if s in ops and t in tensors:
            prod[t].append(s)
        elif s in tensors and t in ops:
            cons[s].append(t)
    shared = {}                                    # 逻辑张量 -> (大小, {核: [读它的子图]})
    for tid, t in tensors.items():
        if t.get('pos') == 'DDR':
            continue
        readers = collections.defaultdict(set)
        for o in cons.get(tid, ()):
            if o in n2s:
                readers[core_of_sg[n2s[o]]].add(n2s[o])
        src = prod.get(tid, [])
        src_core = None
        if src and src[0] in n2s:                   # 中间张量：生产者所在核的消费者不经 DDR
            src_core = core_of_sg[n2s[src[0]]]
            readers.pop(src_core, None)
        elif not (src and ops[src[0]]['op'] == 'COPY_IN'):
            continue
        if len(readers) >= 2:
            shared[tid] = (t['size'], {c: sorted(s) for c, s in readers.items()})
    return shared


def stagger(g, plan):
    shared = shared_tensors(g, plan)
    if not shared:
        return plan
    k = len(plan['core_schedules'])
    load = [0] * k
    score = collections.Counter()
    for tid, (size, readers) in sorted(shared.items(), key=lambda x: -x[1][0]):
        leader = min(readers, key=lambda c: (load[c], c))
        load[leader] += size
        for c, sgs in readers.items():
            for s in sgs:
                score[s] += size if c == leader else -size
    info = derive_multicore_plan(g, plan)
    succ, indeg = info['subgraph_succs'], {s: len(info['subgraph_preds'][s]) for s in info['subgraph_ids']}
    pos = {sg: i for order in plan['core_schedules'] for i, sg in enumerate(order)}
    heap = [(-score[s], pos[s], s) for s in info['subgraph_ids'] if indeg[s] == 0]
    heapq.heapify(heap)
    gorder = []
    while heap:
        _, _, s = heapq.heappop(heap)
        gorder.append(s)
        for t in succ[s]:
            indeg[t] -= 1
            if indeg[t] == 0:
                heapq.heappush(heap, (-score[t], pos[t], t))
    core_of = info['core_by_subgraph']
    new = [[s for s in gorder if core_of[s] == c] for c in range(k)]
    return {'node_to_subgraph': plan['node_to_subgraph'], 'core_schedules': new}
