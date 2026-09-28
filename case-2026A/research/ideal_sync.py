# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""含同步代价的可达下界：理想表调度 + 跨核边固定同步延迟。

理想下界(ideal_bound.py)把通信置零，对小图过于乐观——场景B跨核同步固定 500 cycles，
场景A跨核 Task 等待 1000 cycles。本文件在同一调度器里加入该延迟，给出更诚实的可达值。

仍是乐观下界：忽略 DDR 带宽争用与核内缓存换入换出，只计跨核固定延迟。
"""
import json, sys, os, heapq, collections
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from algos import load_dag

PIPES = ('PIPE_M', 'PIPE_V', 'PIPE_MTE2', 'PIPE_MTE3')


def run(path, sync, ks=(2, 3, 4, 5)):
    g = json.load(open(path))
    elig, cpred, csucc, info = load_dag(g)
    out = {'case': os.path.basename(path)[:-5], 'sync': sync}
    # 反向关键路径当优先级
    indeg = {i: len(cpred[i]) for i in elig}
    q = collections.deque(i for i in elig if indeg[i] == 0)
    topo = []
    while q:
        i = q.popleft(); topo.append(i)
        for j in csucc[i]:
            indeg[j] -= 1
            if indeg[j] == 0: q.append(j)
    blev = {}
    for i in reversed(topo):
        blev[i] = info[i][1] + max((blev[j] for j in csucc[i]), default=0)

    for k in ks:
        avail = {(c, p): 0.0 for c in range(k) for p in PIPES}
        core_of, fin = {}, {}
        rem = {i: len(cpred[i]) for i in elig}
        ready = [(-blev[i], i) for i in elig if rem[i] == 0]
        heapq.heapify(ready)
        mk = 0.0
        while ready:
            _, v = heapq.heappop(ready)
            p, cyc = info[v]
            bestc, bestf = 0, None
            for c in range(k):
                est = avail[(c, p)]
                for u in cpred[v]:
                    t = fin[u] + (sync if core_of[u] != c else 0.0)
                    if t > est: est = t
                f = est + cyc
                if bestf is None or f < bestf:
                    bestc, bestf = c, f
            core_of[v] = bestc; fin[v] = bestf; avail[(bestc, p)] = bestf
            if bestf > mk: mk = bestf
            for w in csucc[v]:
                rem[w] -= 1
                if rem[w] == 0:
                    heapq.heappush(ready, (-blev[w], w))
        out[f'k{k}'] = mk
    return out


def _b(a): return run(a[0], a[1])


if __name__ == '__main__':
    files = sorted(sys.argv[1:])
    jobs = [(f, s) for f in files for s in (500.0, 1000.0)]
    with ProcessPoolExecutor(max_workers=3) as ex:
        rows = list(ex.map(_b, jobs))
    json.dump(rows, open(os.path.join(os.path.dirname(__file__), '..', 'runs', 'ideal_sync.json'), 'w'), indent=1)
    print(f'完成 {len(rows)} 条')
