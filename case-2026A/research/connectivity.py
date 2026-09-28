# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""看收缩后 op-DAG 的弱连通分量结构：决定切图是'装箱'还是'真 min-cut'。"""
import json, sys, os, collections
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pkg', 'code'))
from stub_multicore_cut_and_schedule import _build_op_adjacency, _contract_excluded_copy_nodes

EXCLUDED = {'COPY_IN', 'COPY_OUT'}


def analyze(path):
    g = json.load(open(path))
    _, succs = _build_op_adjacency(g)
    elig = sorted(o['id'] for o in g['ops'] if o['op'] not in EXCLUDED)
    cpred, csucc = _contract_excluded_copy_nodes(elig, succs)
    cyc = {o['id']: (o.get('cycles') or 0) for o in g['ops']}

    # 弱连通分量（并查集）
    par = {i: i for i in elig}
    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    def uni(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: par[ra] = rb
    for a in elig:
        for b in csucc[a]:
            uni(a, b)
    comp = collections.defaultdict(list)
    for i in elig:
        comp[find(i)].append(i)
    sizes = sorted((len(v) for v in comp.values()), reverse=True)
    weights = sorted((sum(cyc[i] for i in v) for v in comp.values()), reverse=True)
    tot_w = sum(weights) or 1
    n_edges = sum(len(csucc[a]) for a in elig)
    return {
        'case': os.path.basename(path).replace('.json', ''),
        'n_ops': len(elig), 'n_comp': len(comp),
        'top_comp_frac_ops': sizes[0] / len(elig) if elig else 0,
        'top_comp_frac_cyc': weights[0] / tot_w,
        'comp_sizes_top5': sizes[:5],
        'n_contracted_edges': n_edges,
        'avg_degree': n_edges / max(len(elig), 1),
    }


if __name__ == '__main__':
    files = sorted(sys.argv[1:])
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(analyze, files))
    json.dump(rows, open(os.path.join(os.path.dirname(__file__), '..', 'runs', 'connectivity.json'), 'w'), indent=1)
    import statistics
    print(f"{'case':10} {'ops':>6} {'分量数':>7} {'最大分量占算力':>14} {'平均出度':>8}")
    for r in rows[:15]:
        print(f"{r['case']:10} {r['n_ops']:6d} {r['n_comp']:7d} "
              f"{r['top_comp_frac_cyc']*100:13.1f}% {r['avg_degree']:8.2f}")
    print('...')
    ncomp = [r['n_comp'] for r in rows]
    frac = [r['top_comp_frac_cyc'] for r in rows]
    print(f"\n分量数: 中位={statistics.median(ncomp):.0f} 最小={min(ncomp)} 最大={max(ncomp)}")
    print(f"最大分量占总算力: 中位={statistics.median(frac)*100:.1f}%  "
          f"最大={max(frac)*100:.1f}%  最小={min(frac)*100:.1f}%")
    print(f"单一巨型分量(>80%算力)的用例: {sum(1 for f in frac if f > 0.8)}/100")
    print(f"多分量(>=5 个)的用例: {sum(1 for n in ncomp if n >= 5)}/100")
    print(f"平均出度: 中位={statistics.median(r['avg_degree'] for r in rows):.2f}")
