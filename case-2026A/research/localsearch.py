# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""以官方评估器为目标函数的局部搜索。

从组合最优方案出发，做四类邻域动作，爬山接受改进解：
  move  : 把一个子图挪到另一个核
  swap  : 交换两个子图所在的核
  merge : 把同核相邻的两个子图并成一个（降子图数——实测这是最关键的方向）
  split : 把一个子图按其内部拓扑序切成两半（涨并行度）

合法性用官方 derive_multicore_plan 预检（纯图运算，比跑评估器便宜两个数量级），
非法的动作直接丢弃，不浪费评估预算。评估预算按用例规模自适应。
"""
import json, os, sys, random, subprocess, tempfile, time, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pkg', 'code'))
from stub_multicore_cut_and_schedule import derive_multicore_plan, MulticoreCutError
from algos import load_dag

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PY = sys.executable
CFG = os.path.join(ROOT, 'pkg', 'data', 'config.txt')


def evaluate(gpath, plan, problem, workdir):
    pp = os.path.join(workdir, 'plan.json')
    json.dump(plan, open(pp, 'w'))
    ev = os.path.join(ROOT, 'pkg', 'code', f'multicore_cut_evaluate_problem_{problem}.py')
    r = subprocess.run(
        [PY, ev, gpath, pp, '--config', CFG,
         '-o', os.path.join(workdir, 'r.json'),
         '--trace-output', os.path.join(workdir, 't.json'),
         '--log-output', os.path.join(workdir, 'l.txt')],
        capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        return None
    return json.load(open(os.path.join(workdir, 'r.json')))['makespan']


def legal(g, plan):
    try:
        derive_multicore_plan(g, plan)
        return True
    except MulticoreCutError:
        return False
    except Exception:
        return False


def _copy(plan):
    return {'node_to_subgraph': dict(plan['node_to_subgraph']),
            'core_schedules': [list(c) for c in plan['core_schedules']]}


def neighbors(plan, rng, topo_rank, n=1):
    """随机产生一个邻域方案；返回 None 表示这次没造出结构上可尝试的动作。"""
    p = _copy(plan)
    cs = p['core_schedules']
    k = len(cs)
    nonempty = [i for i in range(k) if cs[i]]
    if not nonempty:
        return None
    op = rng.choice(['move', 'swap', 'merge', 'merge', 'split'])

    if op == 'move':
        src = rng.choice(nonempty)
        dst = rng.randrange(k)
        if dst == src:
            return None
        sg = cs[src].pop(rng.randrange(len(cs[src])))
        # 插到目标核里保持全局拓扑秩升序
        pos = 0
        while pos < len(cs[dst]) and topo_rank.get(cs[dst][pos], 0) < topo_rank.get(sg, 0):
            pos += 1
        cs[dst].insert(pos, sg)
        return p

    if op == 'swap':
        if len(nonempty) < 2:
            return None
        a, b = rng.sample(nonempty, 2)
        i, j = rng.randrange(len(cs[a])), rng.randrange(len(cs[b]))
        cs[a][i], cs[b][j] = cs[b][j], cs[a][i]
        cs[a].sort(key=lambda s: topo_rank.get(s, 0))
        cs[b].sort(key=lambda s: topo_rank.get(s, 0))
        return p

    if op == 'merge':
        cand = [c for c in nonempty if len(cs[c]) >= 2]
        if not cand:
            return None
        c = rng.choice(cand)
        i = rng.randrange(len(cs[c]) - 1)
        keep, gone = cs[c][i], cs[c][i + 1]
        for nid, sid in p['node_to_subgraph'].items():
            if sid == gone:
                p['node_to_subgraph'][nid] = keep
        cs[c].pop(i + 1)
        return p

    # split：按子图内部的全局拓扑秩切两半
    c = rng.choice(nonempty)
    i = rng.randrange(len(cs[c]))
    sg = cs[c][i]
    nodes = [int(n) for n, s in p['node_to_subgraph'].items() if s == sg]
    if len(nodes) < 4:
        return None
    nodes.sort()
    new_id = max(p['node_to_subgraph'].values()) + 1
    half = len(nodes) // 2
    for n in nodes[half:]:
        p['node_to_subgraph'][str(n)] = new_id
    cs[c].insert(i + 1, new_id)
    topo_rank[new_id] = topo_rank.get(sg, 0) + 0.5
    return p


def search(case, plan0, problem, budget_sec=60.0, seed=0, verbose=False):
    gpath = os.path.join(ROOT, 'pkg', 'data', case + '.json')
    g = json.load(open(gpath))
    rng = random.Random(seed)
    topo_rank = {}
    for c in plan0['core_schedules']:
        for i, sg in enumerate(c):
            topo_rank[sg] = sg          # 子图 id 本身即按拓扑序生成
    with tempfile.TemporaryDirectory() as td:
        best = evaluate(gpath, plan0, problem, td)
        if best is None:
            return None, None, 0
        bestplan = plan0
        t0 = time.time()
        tries = accepted = 0
        while time.time() - t0 < budget_sec:
            cand = neighbors(bestplan, rng, topo_rank)
            if cand is None or not legal(g, cand):
                continue
            tries += 1
            m = evaluate(gpath, cand, problem, td)
            if m is not None and m < best:
                best, bestplan = m, cand
                accepted += 1
                if verbose:
                    print(f'    +{accepted} makespan={m:,} '
                          f'sg={len(set(cand["node_to_subgraph"].values()))}', flush=True)
        return best, bestplan, tries
