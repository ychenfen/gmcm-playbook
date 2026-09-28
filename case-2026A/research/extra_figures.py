# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""模型检验用的三张补充图（只读 runs/ 与 deliverables/，不调用评估器）：

  nsg_quality   子图数与方案质量：同一用例 4 核的全部扫描候选，Makespan 相对该用例最优值的比，按子图数分组（问题1 / 问题2）
  cross_depth   换核深度：最终方案商图上最长路径的换核次数 h，与 (实测 Makespan − 零通信理想 Makespan) 的关系（问题1 / 问题2）
  cache_bound   缓存收益的带宽上限：γ_上限 = (DDR 字节 + 命中字节) / DDR 字节，与同一方案实测 γ 的对比（问题3，4 核）

输出 paper/fig/<名>.pdf/.png，图中数字另存 paper/fig/fig_numbers_extra.json（由 numbers_tex.py 读入，前缀 figx_）。
"""
import json, os, sys, glob, collections, statistics as st, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_figures as MF                                   # 复用统一字体、配色与尺寸
from make_figures import plt, C1, C2, C3, INK, INK2, REF, NEUTRAL, FULL, HALF
from algos import load_dag

ROOT = MF.ROOT
OUT = os.path.join(ROOT, 'paper', 'fig')
D = os.path.join(ROOT, 'deliverables')
NUM = {}


def save(fig, name):
    MF.nature_panels(fig)
    fig.savefig(os.path.join(OUT, name + '.pdf')); fig.savefig(os.path.join(OUT, name + '.png'), dpi=240)
    plt.close(fig); print('  写出', name)


def nsg_quality():
    best = collections.defaultdict(lambda: 1 << 62)
    rows = []
    for f in glob.glob(os.path.join(ROOT, 'runs', 'pf', '*_k4_*.json')):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if r.get('makespan') and 'err' not in r and r['k'] == 4 and r['problem'] in (1, 2) and r.get('n_subgraphs'):
            key = (r['problem'], r['case']); best[key] = min(best[key], r['makespan'])
            rows.append((r['problem'], r['case'], r['n_subgraphs'], r['makespan']))
    edges = [1, 4, 16, 64, 256, 1024, 10 ** 9]
    labs = ['1~3', '4~15', '16~63', '64~255', '256~1023', '≥1024']
    fig, ax = plt.subplots(figsize=(FULL * 0.62, 2.5))
    for p, col, mk, name in ((1, C1, 'o', '问题一 · 场景A'), (2, C2, 's', '问题二 · 场景B')):
        med, n = [], []
        for lo, hi in zip(edges, edges[1:]):
            v = [m / best[(pp, c)] for pp, c, s_, m in rows if pp == p and lo <= s_ < hi]
            med.append(st.median(v) if v else float('nan')); n.append(len(v))
        ax.plot(range(len(labs)), med, color=col, marker=mk, label=name)
        NUM[f'nsg_p{p}_median'] = med; NUM[f'nsg_p{p}_n'] = n
    ax.set_xticks(range(len(labs))); ax.set_xticklabels(labs); ax.set_xlabel('方案的子图数')
    ax.set_ylabel('Makespan / 该用例最优值（中位数）'); ax.legend(loc='upper left'); ax.axhline(1, color=REF, lw=0.8)
    NUM['nsg_pairs'] = len(rows)
    conn = {r['case']: r['top_comp_frac_cyc'] for r in json.load(open(os.path.join(ROOT, 'runs', 'connectivity.json')))}
    hi = [c for pp, c, s_, m in rows if pp == 1 and s_ >= 256]
    NUM['nsg_hi_n'] = len(hi); NUM['nsg_hi_famIII_pct'] = sum(1 for c in hi if conn[c] < 0.3) / max(1, len(hi)) * 100
    save(fig, 'nsg_quality')


def quotient_cross_depth(g, plan):
    """商图上最长路径的换核次数（按拓扑序动态规划）。"""
    elig, cpred, csucc, info = load_dag(g)
    sg = {int(k): v for k, v in plan['node_to_subgraph'].items()}
    core = {s: c for c, order in enumerate(plan['core_schedules']) for s in order}
    succ = collections.defaultdict(set)
    for u in elig:
        for v in csucc[u]:
            if sg[u] != sg[v]:
                succ[sg[u]].add(sg[v])
    nodes = set(sg.values())
    indeg = collections.Counter(v for u in succ for v in succ[u])
    q = [s for s in nodes if indeg[s] == 0]; depth = {s: 0 for s in nodes}
    while q:
        u = q.pop()
        for v in succ[u]:
            depth[v] = max(depth[v], depth[u] + (core[u] != core[v]))
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    return max(depth.values()) if depth else 0


def cross_depth():
    ideal = {r['case']: r for r in json.load(open(os.path.join(ROOT, 'runs', 'ideal_bound.json')))}
    fig, axes = plt.subplots(1, 2, figsize=(FULL, 2.5))
    for ax, p, delta, col, tt in ((axes[0], 1, 1000, C1, '(a) 问题一 · 场景A'), (axes[1], 2, 500, C2, '(b) 问题二 · 场景B')):
        xs, ys = [], []
        for f in sorted(glob.glob(os.path.join(D, 'evals', f'p{p}_k4_case_*.json'))):
            e = json.load(open(f)); c = e['case']
            g = json.load(open(os.path.join(ROOT, 'pkg', 'data', c + '.json')))
            plan = json.load(open(os.path.join(D, 'plans', f'p{p}_k4_{c}.json')))
            h = quotient_cross_depth(g, plan)
            xs.append(h * delta); ys.append(max(e['makespan'] - ideal[c]['ideal_4'], 1))
        ax.scatter(xs, ys, s=10, color=col, alpha=0.75, linewidths=0)
        lim = [1, max(max(xs), max(ys)) * 1.5]
        ax.plot(lim, lim, color=REF, lw=0.8, ls='--'); ax.set_xscale('symlog', linthresh=100); ax.set_yscale('log')
        ax.set_xlabel(f'换核深度 h × {delta}（周期）'); ax.set_title(tt)
        lx = [math.log10(x) for x, y in zip(xs, ys) if x > 0]; ly = [math.log10(y) for x, y in zip(xs, ys) if x > 0]
        mx, my = st.mean(lx), st.mean(ly)
        r = sum((a - mx) * (b - my) for a, b in zip(lx, ly)) / math.sqrt(sum((a - mx) ** 2 for a in lx) * sum((b - my) ** 2 for b in ly))
        NUM[f'depth_p{p}_corr'] = r; NUM[f'depth_p{p}_hmedian'] = st.median(x / delta for x in xs)
        NUM[f'depth_p{p}_above'] = sum(1 for x, y in zip(xs, ys) if y >= x)
        NUM[f'depth_p{p}_n'] = len(xs); NUM[f'depth_p{p}_zero'] = sum(1 for x in xs if x == 0)
    axes[0].set_ylabel('实测 − 零通信理想（周期）')
    fig.tight_layout(w_pad=2)
    save(fig, 'cross_depth')


def cache_bound():
    cd = {r['case']: r for r in json.load(open(os.path.join(D, 'analysis', 'cache_diag_k4.json')))}
    xs, ys, bs = [], [], []
    for c, r in cd.items():
        hit = r['bytes'].get('hit', 0); ddr = r['ddr_bytes']
        if ddr <= 0:
            continue
        m3 = json.load(open(os.path.join(D, 'evals', f'p3_k4_{c}.json')))['makespan']
        m2 = json.load(open(os.path.join(D, 'evals', f'p2x_k4_{c}.json')))['makespan']
        xs.append((ddr + hit) / ddr); ys.append(m2 / m3); bs.append((ddr + hit) / 60 / m2)
    fig, ax = plt.subplots(figsize=(FULL * 0.62, 2.6))
    groups = ((0, .3, NEUTRAL, 'o', 'β < 30%'), (.3, .6, C1, 's', '30% ≤ β < 60%'), (.6, 99, C2, 'D', 'β ≥ 60%'))
    for lo, hi, col, mk, lab in groups:
        pts = [(x, y) for x, y, b in zip(xs, ys, bs) if lo <= b < hi]
        ax.scatter([x for x, _ in pts], [y for _, y in pts], s=13, color=col, marker=mk, label=lab, linewidths=0, alpha=0.85)
    lim = [0.97, max(xs) * 1.05]
    ax.plot(lim, lim, color=REF, lw=0.8, ls='--'); ax.set_xscale('log')
    ticks = [1, 1.5, 2, 3, 4]; ax.set_xticks(ticks); ax.set_xticklabels([f'{t:g}' for t in ticks]); ax.minorticks_off()
    ax.set_xlabel('带宽上限 γ_上限 =（DDR+命中）/ DDR 字节'); ax.set_ylabel('实测 γ（同一方案）')
    ax.legend(loc='upper left', fontsize=7.4)
    NUM['cb_n'] = len(xs); NUM['cb_below'] = sum(1 for x, y in zip(xs, ys) if y <= x * 1.001)
    NUM['cb_ratio_hi'] = st.median([(y - 1) / (x - 1) for x, y, b in zip(xs, ys, bs) if b >= .6 and x > 1.01] or [0])
    NUM['cb_ratio_lo'] = st.median([(y - 1) / (x - 1) for x, y, b in zip(xs, ys, bs) if b < .3 and x > 1.01] or [0])
    save(fig, 'cache_bound')


def final_timeline(case='case_002', k=4):
    """case_002 问题一、问题二最终方案（4 核）的逐核时间线，各出一张图，由官方评估程序在固定配置下重新评估。"""
    import subprocess, tempfile
    for p in (1, 2):
        fig, ax = plt.subplots(1, 1, figsize=(FULL, 1.75))
        with tempfile.TemporaryDirectory() as td:
            subprocess.run([sys.executable, os.path.join(ROOT, 'pkg', 'code', f'multicore_cut_evaluate_problem_{p}.py'),
                            os.path.join(ROOT, 'pkg', 'data', case + '.json'), os.path.join(D, 'plans', f'p{p}_k{k}_{case}.json'),
                            '--config', os.path.join(ROOT, 'pkg', 'data', 'config.txt'), '-o', td + '/r.json',
                            '--trace-output', td + '/t.json', '--log-output', td + '/l.txt'], check=True, capture_output=True)
            r = json.load(open(td + '/r.json'))
        for core in r['per_core_timeline']:
            c = core['core_id']; y = (k - 1 - c) * 1.0
            comp = [(o['start'], o['end'] - o['start']) for o in core['ops'] if o['pipe'] in ('PIPE_M', 'PIPE_V') and o['end'] > o['start']]
            copy = [(o['start'], o['end'] - o['start']) for o in core['ops'] if o['pipe'] in ('PIPE_MTE2', 'PIPE_MTE3') and o['end'] > o['start']]
            ax.broken_barh(comp, (y + 0.42, 0.40), facecolors=C1, linewidth=0)
            ax.broken_barh(copy, (y + 0.02, 0.36), facecolors=C2, linewidth=0)
        ms = r['makespan']; ax.axvline(ms, color=INK, linewidth=0.8)
        ax.annotate(f'makespan {ms:,}', (ms, k - 0.1), xytext=(4, 0), textcoords='offset points', fontsize=7.5, va='top')
        ax.set_yticks([k - 1 - c + 0.42 for c in range(k)]); ax.set_yticklabels([f'核{c}' for c in range(k)])
        ax.set_ylim(-0.1, k + 0.05); ax.grid(False); ax.set_xlabel('时间（周期）')
        handles = [plt.Rectangle((0, 0), 1, 1, color=C1, label='计算（Cube/Vector）'),
                   plt.Rectangle((0, 0), 1, 1, color=C2, label='数据搬运（COPY_IN/OUT）')]
        ax.legend(handles=handles, loc='lower right', ncol=2, bbox_to_anchor=(1, 1.0))
        NUM[f'tl_{case}_p{p}_ms'] = ms
        NUM[f'tl_{case}_p{p}_copyMB'] = r['data_movement_bytes']['scheduled_copy_bytes'] / 1e6
        save(fig, f'final_timeline_p{p}')


if __name__ == '__main__':
    for f in (nsg_quality, cross_depth, cache_bound, final_timeline):
        f()
    json.dump(NUM, open(os.path.join(OUT, 'fig_numbers_extra.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(NUM, ensure_ascii=False)[:1500])
