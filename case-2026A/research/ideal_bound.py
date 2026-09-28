# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""理想表调度下界：k 个核、每核 4 条流水线，通信代价置零。

比 max(关键路径, 算力/核数) 紧得多，因为它吃进了 DAG 依赖结构造成的装箱损失。
若某用例的理想下界远高于解析下界，说明它是结构受限，不是算法不行。
"""
import json, sys, os, heapq, collections
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from algos import load_dag

PIPES = ['PIPE_M', 'PIPE_V', 'PIPE_MTE2', 'PIPE_MTE3']


def ideal(path, ks=(1, 2, 3, 4, 5)):
    g = json.load(open(path))
    elig, cpred, csucc, info = load_dag(g)
    out = {'case': os.path.basename(path)[:-5]}
    for k in ks:
        avail = {(c, p): 0.0 for c in range(k) for p in PIPES}
        nsucc = {i: len(cpred[i]) for i in elig}
        ready = [(0.0, i) for i in elig if nsucc[i] == 0]
        heapq.heapify(ready)
        done = {}
        pending = dict(nsucc)
        makespan = 0.0
        while ready:
            est, i = heapq.heappop(ready)
            p, cyc = info[i]
            # 选最早可用的 (核, 对应流水)
            best = min(range(k), key=lambda c: max(avail[(c, p)], est))
            start = max(avail[(best, p)], est)
            fin = start + cyc
            avail[(best, p)] = fin
            done[i] = fin
            makespan = max(makespan, fin)
            for j in csucc[i]:
                pending[j] -= 1
                if pending[j] == 0:
                    rdy = max(done[x] for x in cpred[j]) if cpred[j] else 0.0
                    heapq.heappush(ready, (rdy, j))
        out[f'ideal_{k}'] = makespan
    return out


if __name__ == '__main__':
    files = sorted(sys.argv[1:])
    with ProcessPoolExecutor(max_workers=4) as ex:
        rows = list(ex.map(ideal, files))
    json.dump(rows, open(os.path.join(os.path.dirname(__file__), '..', 'runs', 'ideal_bound.json'), 'w'), indent=1)
    print(f'完成 {len(rows)} 个用例')
