# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
# 人工智能工具：OpenAI Codex（ChatGPT 桌面应用），版本/型号：【待团队按会话记录填写】，开发机构：OpenAI，版本发布日期：【待填写】
"""论文全部数据图。只读 deliverables/ 与 runs/，不手写任何数字；图注草稿连同其中数字一并写入 paper/fig/captions.md。

用法: /opt/homebrew/opt/python@3.11/bin/python3.11 src/make_figures.py [图名 ...]
输出: paper/fig/<名>.pdf（排版）与 .png（预览）

风格：Times New Roman（西文/数字）+ 宋体（中文）；全宽 5.9in / 半宽 2.85in，与 A4 版心一致，排版时不缩放。
配色：dataviz 参考调色板前三槽（蓝 #2a78d6 / 橙 #eb6834 / 青 #1baf7a），validate_palette.js --pairs all 通过；
青色对白底 2.74:1，故一律配直接标注或图例 + 不同标记形状，黑白打印可辨。量纲不同分面板，不用双纵轴；
说明文字不放图内，交给 LaTeX \\caption。
"""
import json, os, re, sys, glob, math, collections, statistics as st, argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
OUT = os.path.join(ROOT, 'paper', 'fig')
CACHE_DIAG = os.path.join(ROOT, 'deliverables', 'analysis', 'cache_diag_k4.json')
os.makedirs(OUT, exist_ok=True)

# Songti.ttc 的第一个字重是 Black（特粗），matplotlib 只读第一个字重；优先用抽出的常规体（见 paper/tex 说明）。
_SONG_REG = os.path.expanduser('~/.cache/figstyle/SongtiSC-Regular.ttf')
if not os.path.exists(_SONG_REG):
    from fontTools.ttLib import TTCollection
    for _f in TTCollection('/System/Library/Fonts/Supplemental/Songti.ttc').fonts:
        if _f['name'].getDebugName(1) == 'Songti SC' and _f['name'].getDebugName(2) == 'Regular':
            os.makedirs(os.path.dirname(_SONG_REG), exist_ok=True)
            _f.save(_SONG_REG)
            break
for f in ('/System/Library/Fonts/Supplemental/Times New Roman.ttf', _SONG_REG):
    font_manager.fontManager.addfont(f)
C1, C2, C3 = '#2a78d6', '#eb6834', '#1baf7a'
INK, INK2, GRID, REF, NEUTRAL = '#0b0b0b', '#52514e', '#e4e3de', '#9a9892', '#cfcdc6'
FULL, HALF = 5.9, 2.85
BLUES = LinearSegmentedColormap.from_list('blues', ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'])
plt.rcParams.update({
    'font.family': ['Times New Roman', 'Songti SC'], 'mathtext.fontset': 'stix', 'axes.unicode_minus': False,
    'font.size': 8.5, 'axes.titlesize': 9, 'axes.labelsize': 8.5, 'xtick.labelsize': 8, 'ytick.labelsize': 8,
    'legend.fontsize': 7.8, 'axes.edgecolor': INK2, 'axes.labelcolor': INK, 'xtick.color': INK2, 'ytick.color': INK2,
    'axes.linewidth': 0.7, 'xtick.major.width': 0.7, 'ytick.major.width': 0.7, 'xtick.major.size': 2.5,
    'ytick.major.size': 2.5, 'axes.spines.top': False, 'axes.spines.right': False, 'axes.grid': True,
    'axes.grid.axis': 'y', 'axes.axisbelow': True, 'grid.color': GRID, 'grid.linestyle': '-', 'grid.linewidth': 0.5,
    'legend.frameon': False, 'lines.linewidth': 1.5, 'lines.markersize': 4.5, 'figure.dpi': 150,
    'savefig.bbox': 'tight', 'savefig.pad_inches': 0.03, 'axes.titlelocation': 'left', 'axes.titlepad': 5,
})
CAP = collections.OrderedDict()
FIGNUM = {}                                           # 图注中的数字，供论文宏使用（fig_numbers.json）                       # 图名 -> 图注草稿


def nature_panels(fig):
    """把 '(a) 标题' 形式的子图标题改成左上角粗体小写字母 + 常规标题（Nature 风格）。"""
    for ax in fig.axes:
        t = ax.get_title(loc='left') or ax.get_title()
        m = re.match(r'^\(([a-z])\)\s*(.*)$', t)
        if not m:
            continue
        ax.set_title('', loc='left'); ax.set_title('')
        ax.set_title(m.group(2), loc='left', fontsize=8.5, pad=5)
        ax.text(-0.02, 1.0, m.group(1), transform=ax.transAxes, ha='right', va='bottom',
                fontsize=11, fontweight='bold', family='Times New Roman')


def save(fig, name, caption):
    nature_panels(fig)
    fig.savefig(os.path.join(OUT, name + '.pdf'))
    fig.savefig(os.path.join(OUT, name + '.png'), dpi=240)
    plt.close(fig)
    CAP[name] = caption
    print('  写出', name)


def end_label(ax, x, y, text, dy=0, color=INK):
    ax.annotate(text, (x, y), xytext=(5, dy), textcoords='offset points', va='center', color=color, fontsize=7.8)


# ---------------------------------------------------------------- 数据

def load(deliverables=None):
    D = {}
    sc = {}
    for f in glob.glob(os.path.join(ROOT, 'runs/singlecore/case_[0-9][0-9][0-9].log')):
        m = re.search(r'makespan=([\d,]+)', open(f).read())
        if m:
            sc[os.path.basename(f)[:-4]] = int(m.group(1).replace(',', ''))
    D['sc'] = sc
    D['cases'] = sorted(sc)
    directory = deliverables or os.path.join(ROOT, 'deliverables')
    status = json.load(open(os.path.join(directory, 'finalize_status.json')))
    if not status.get('verified'):
        raise ValueError('deliverables have not passed final verification')
    D['ev'] = {os.path.basename(f)[:-5]: json.load(open(f)) for f in glob.glob(os.path.join(directory, 'evals/*.json'))}
    D['ch'] = {r['case']: r for r in json.load(open(os.path.join(ROOT, 'runs/characterize.json')))}
    D['cn'] = {r['case']: r for r in json.load(open(os.path.join(ROOT, 'runs/connectivity.json')))}
    isy = {}
    for r in json.load(open(os.path.join(ROOT, 'runs/ideal_sync.json'))):
        isy[(r['case'], r['sync'])] = r
    D['isy'] = isy
    pf = []
    for f in glob.glob(os.path.join(ROOT, 'runs/pf/*.json')):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if 'err' not in r and r.get('makespan'):
            pf.append(r)
    D['pf'] = pf
    return D


def family(D, c):
    t = D['cn'][c]['top_comp_frac_cyc']
    return 'I' if t > 0.8 else ('II' if t > 0.3 else 'III')


FAMC = {'I': C1, 'II': C2, 'III': C3}
FAMM = {'I': 'o', 'II': 's', 'III': 'D'}
FAML = {'I': 'I 单一巨块', 'II': 'II 主块+碎片', 'III': 'III 多分量'}


def sp(D, p, k, c):
    if k == 1 and p in (1, 2):
        return 1.0
    e = D['ev'].get(f'p{p}_k{k}_{c}')
    return D['sc'][c] / e['makespan'] if e and 'makespan' in e else None


def ref(D, p, k, c):
    if k == 1:
        return 1.0
    r = D['isy'].get((c, 1000.0 if p == 1 else 500.0))
    return D['sc'][c] / r[f'k{k}'] if r else None


def pairs(D, pa, pb):
    """同一构造方案 (用例, k, 算法, 参数, keff) 在两个问题下都评过的配对。"""
    rec = collections.defaultdict(dict)
    for r in D['pf']:
        rec[(r['case'], r['k'], r['algo'], r['div'], r.get('keff') or r['k'])][r['problem']] = r
    return [(v[pa], v[pb]) for v in rec.values() if pa in v and pb in v]


# ---------------------------------------------------------------- 图

def f_dataset(D):
    fig, (a, b) = plt.subplots(1, 2, figsize=(FULL, 2.4), gridspec_kw={'width_ratios': [1.25, 1]})
    fams = collections.Counter()
    for c in D['cases']:
        f = family(D, c); fams[f] += 1
        tot = D['ch'][c]['cyc_M'] + D['ch'][c]['cyc_V']
        a.scatter(math.log10(tot), D['cn'][c]['top_comp_frac_cyc'] * 100, s=14, color=FAMC[f], marker=FAMM[f],
                  linewidths=0, alpha=0.85)
    for y in (30, 80):
        a.axhline(y, color=REF, linewidth=0.7)
    for f, y in (('I', 90), ('II', 55), ('III', 12)):
        a.text(7.9, y, f'{FAML[f]}（{fams[f]}）', color=INK, fontsize=7.6, ha='right', va='center')
    a.set_xlabel('总计算周期（lg）'); a.set_ylabel('最大连通分量占总算力 (%)')
    a.set_title('(a) 连通结构与规模'); a.set_ylim(-4, 104)
    w = [(D['ch'][c]['cyc_M'] + D['ch'][c]['cyc_V']) / max(D['ch'][c]['crit_path'], 1) for c in D['cases']]
    bins = [10 ** (x / 4) for x in range(0, 17)]
    b.hist(w, bins=bins, color=C1, edgecolor='white', linewidth=0.8)
    b.set_xscale('log'); b.set_xlabel('DAG 宽度比（总算力 / 关键路径）'); b.set_ylabel('用例数')
    b.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    fig.subplots_adjust(wspace=0.32)
    med = st.median(w)
    b.axvline(med, color=INK2, linewidth=0.8)
    b.annotate(f'中位 {med:.0f}', (med, b.get_ylim()[1] * 0.92), xytext=(4, 0), textcoords='offset points', fontsize=7.6)
    b.set_title('(b) 可并行度')
    save(fig, 'dataset_profile',
         f'测试集结构刻画（100 个用例）。(a) 以最大弱连通分量占总算力的比例划分三类：单一巨块 {fams["I"]} 例、'
         f'主块+碎片 {fams["II"]} 例、多分量 {fams["III"]} 例；(b) 总算力与关键路径之比的中位数为 {med:.0f}，'
         f'绝大多数计算图结构上可充分并行。')


def f_bounds(D):
    fig, axes = plt.subplots(1, 2, figsize=(FULL, 2.55), sharey=True)
    out = {}
    for ax, p, tt in ((axes[0], 1, '(a) 问题1 · 场景A'), (axes[1], 2, '(b) 问题2 · 场景B')):
        xs, ys = [], []
        for c in D['cases']:
            x, y = ref(D, p, 4, c), sp(D, p, 4, c)
            if x and y:
                f = family(D, c)
                ax.scatter(x, y, s=12, color=FAMC[f], marker=FAMM[f], linewidths=0, alpha=0.85)
                xs.append(x); ys.append(y)
        lim = max(max(xs), max(ys)) * 1.05
        ax.plot([0, lim], [0, lim], color=REF, linewidth=0.8)
        ax.text(lim * 0.97, lim * 0.97, '$y=x$', color=REF, fontsize=7.5, ha='right', va='bottom')
        ach = st.mean(ys) / st.mean(xs)
        out[p] = (st.mean(ys), st.mean(xs), ach, sum(y > x for x, y in zip(xs, ys)))
        ax.set_xlim(0, lim); ax.set_ylim(0, lim); ax.set_title(tt)
        ax.set_xlabel('可达参考加速比（4 核）')
        ax.grid(True, axis='both')
    axes[0].set_ylabel('本文实测加速比（4 核）')
    handles = [plt.Line2D([], [], marker=FAMM[f], color=FAMC[f], linestyle='', markersize=5, label=FAML[f]) for f in FAML]
    axes[1].legend(handles=handles, loc='lower right')
    save(fig, 'bounds_gap',
         f'逐用例实测加速比与含同步代价的可达参考（4 核）。可达参考由忽略 DDR 争用、计入固定跨核同步延迟的表调度给出，'
         f'为贪心结果而非严格上界，故少数点位于对角线上方（问题1 {out[1][3]} 例、问题2 {out[2][3]} 例）。'
         f'平均达成率：问题1 {out[1][2]*100:.0f}%，问题2 {out[2][2]*100:.0f}%。')


def f_size(D):
    fig, axes = plt.subplots(1, 2, figsize=(FULL, 2.35), sharey=True)
    rs = {}
    for ax, p, tt in ((axes[0], 1, '(a) 问题1 · 场景A'), (axes[1], 2, '(b) 问题2 · 场景B')):
        pts = []
        for c in D['cases']:
            x = math.log10(D['ch'][c]['cyc_M'] + D['ch'][c]['cyc_V'])
            r, y = ref(D, p, 4, c), sp(D, p, 4, c)
            if r and y:
                pts.append((x, min(y / r, 1.4), family(D, c)))
        for x, y, f in pts:
            ax.scatter(x, y * 100, s=11, color=FAMC[f], marker=FAMM[f], linewidths=0, alpha=0.8)
        edges = [4.0, 4.7, 5.3, 6.0, 6.7, 8.2]
        bx, by = [], []
        for lo, hi in zip(edges, edges[1:]):
            v = [y for x, y, _ in pts if lo <= x < hi]
            if v:
                bx.append((lo + hi) / 2); by.append(st.median(v) * 100)
        ax.plot(bx, by, color=INK, marker='o', markersize=3.5, linewidth=1.3)
        xs, ys = [x for x, _, _ in pts], [y for _, y, _ in pts]
        mx, my = st.mean(xs), st.mean(ys)
        rs[p] = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / math.sqrt(
            sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys))
        ax.set_title(f'{tt}（r = {rs[p]:.2f}）'); ax.set_xlabel('总计算周期（lg）')
    axes[0].set_ylabel('达成率 = 实测 / 可达参考 (%)')
    end_label(axes[1], bx[-1], by[-1], '分箱中位数', dy=8)
    save(fig, 'size_threshold',
         f'规模阈值效应（4 核）。小图的理想 makespan 只有数千至数万周期，固定的跨核同步延迟（场景A 1000、场景B 500 周期）'
         f'占比过高，达成率随之下降。达成率与总计算周期对数的相关系数：问题1 {rs[1]:.2f}，问题2 {rs[2]:.2f}。'
         f'达成率超过 140% 的点截断显示。')


def f_traffic(D):
    P = pairs(D, 1, 2)
    edges = [1, 8, 32, 128, 512, 10 ** 9]
    labs = ['1~7', '8~31', '32~127', '128~511', '≥512']
    tr, ms, n = [], [], []
    for lo, hi in zip(edges, edges[1:]):
        v = [(a, b) for a, b in P if lo <= a['n_subgraphs'] < hi and a.get('added_bytes')]
        n.append(len(v))
        tr.append(st.mean(b['added_bytes'] / a['added_bytes'] for a, b in v) if v else float('nan'))
        ms.append(st.mean(b['makespan'] / a['makespan'] for a, b in v) if v else float('nan'))
    fig, (a, b) = plt.subplots(1, 2, figsize=(FULL, 2.2))
    for ax, vals, tt, yl in ((a, tr, '(a) 额外搬运量 场景B / 场景A', '比值'), (b, ms, '(b) makespan 场景B / 场景A', '比值')):
        ax.bar(range(len(labs)), vals, color=C1, width=0.62)
        ax.axhline(1, color=REF, linewidth=0.8)
        for i, v in enumerate(vals):
            ax.text(i, v - 0.035, f'{v:.2f}', ha='center', va='top', fontsize=7.5, color='white')
        ax.set_xticks(range(len(labs))); ax.set_xticklabels(labs); ax.set_xlabel('子图数'); ax.set_title(tt)
        ax.set_ylim(0, 1.15); ax.set_ylabel(yl)
    FIGNUM['traffic'] = {'pairs': len(P), 'added_ratio': tr, 'ms_ratio': ms, 'n': n}
    save(fig, 'traffic_AB',
         f'同一方案在场景A、B下的对比（{len(P)} 组配对，按子图数分组）。场景B中同核子图的边界不产生搬运，'
         f'子图越多两者差距越大：≥512 个子图时额外搬运量之比为 {tr[-1]:.2f}，makespan 之比为 {ms[-1]:.2f}。'
         f'各组配对数依次为 {"、".join(map(str, n))}。')


def f_spill(D):
    P = pairs(D, 1, 2)
    edges = [0, 5e6, 2e7, 1e8, 1e13]
    labs = ['<5MB', '5~20MB', '20~100MB', '≥100MB']
    frac, share, ms, n = [], [], [], []
    for lo, hi in zip(edges, edges[1:]):
        v = [(a, b) for a, b in P if lo <= D['ch'][a['case']]['mid_bytes'] < hi]
        n.append(len(v))
        frac.append(sum((b.get('spill_bytes') or 0) > 0 for _, b in v) / len(v) * 100)
        share.append(st.mean((b.get('spill_bytes') or 0) / max(b['added_bytes'], 1) for _, b in v) * 100)
        ms.append(st.mean(b['makespan'] / a['makespan'] for a, b in v))
    fig, (a, b) = plt.subplots(1, 2, figsize=(FULL, 2.2))
    x = range(len(labs))
    a.bar([i - 0.19 for i in x], frac, width=0.36, color=C2, label='触发换出的配对比例')
    a.bar([i + 0.19 for i in x], share, width=0.36, color=C1, label='换出字节占额外搬运')
    a.set_xticks(list(x)); a.set_xticklabels(labs); a.set_ylabel('%'); a.set_ylim(0, 122); a.set_yticks(range(0, 101, 20))
    a.set_title('(a) 场景B 的缓存换出'); a.legend(loc='upper left'); a.set_xlabel('计算图中间张量总量')
    b.bar(list(x), ms, color=C1, width=0.62)
    for i, v in enumerate(ms):
        b.text(i, v - 0.035, f'{v:.2f}', ha='center', va='top', fontsize=7.5, color='white')
    b.axhline(1, color=REF, linewidth=0.8)
    b.set_xticks(list(x)); b.set_xticklabels(labs); b.set_ylim(0, 1.15); b.set_ylabel('比值')
    b.set_title('(b) makespan 场景B / 场景A'); b.set_xlabel('计算图中间张量总量')
    FIGNUM['spill'] = {'trigger_pct': frac, 'share_pct': share, 'ms_ratio': ms, 'n': n, 'pairs': sum(n)}
    save(fig, 'spill_B',
         f'场景B 把同核子图合并为一个 Task，工作集可能超出 L1/UB 而触发换入换出。中间张量越大，触发比例越高，'
         f'场景B 相对场景A 的 makespan 优势从 {ms[0]:.2f} 收窄到 {ms[-1]:.2f}（按中间张量总量分组，{sum(n)} 组配对）。')


def f_timeline(D):
    d = json.load(open(os.path.join(ROOT, 'runs/fig_data/timeline_AB.json')))
    fig, axes = plt.subplots(2, 1, figsize=(FULL, 3.0), sharex=True)
    for ax, tag, tt in ((axes[0], 'A', '(a) 场景A'), (axes[1], 'B', '(b) 场景B')):
        k = len(d[tag]['timeline'])
        for core in d[tag]['timeline']:
            c = core['core']
            comp = [(s, e - s) for p, s, e, op in core['ops'] if p in ('PIPE_M', 'PIPE_V') and e > s]
            copy = [(s, e - s) for p, s, e, op in core['ops'] if p in ('PIPE_MTE2', 'PIPE_MTE3') and e > s]
            y = (k - 1 - c) * 1.0
            ax.broken_barh(comp, (y + 0.42, 0.40), facecolors=C1, linewidth=0)
            ax.broken_barh(copy, (y + 0.02, 0.36), facecolors=C2, linewidth=0)
        ms = d[tag]['makespan']
        ax.axvline(ms, color=INK, linewidth=0.8)
        ax.annotate(f'makespan {ms:,}', (ms, k - 0.1), xytext=(4, 0), textcoords='offset points', fontsize=7.5, va='top')
        ax.set_yticks([k - 1 - c + 0.42 for c in range(k)]); ax.set_yticklabels([f'核{c}' for c in range(k)])
        ax.set_ylim(-0.1, k + 0.05); ax.set_title(tt); ax.grid(False)
    axes[1].set_xlabel('时间（周期）')
    handles = [plt.Rectangle((0, 0), 1, 1, color=C1, label='计算（Cube/Vector）'),
               plt.Rectangle((0, 0), 1, 1, color=C2, label='数据搬运（COPY_IN/OUT）')]
    axes[0].legend(handles=handles, loc='upper right', ncol=2, bbox_to_anchor=(1, 1.32))
    FIGNUM['timeline'] = {'case': d['case'], 'k': d['k'], 'msA': d['A']['makespan'], 'msB': d['B']['makespan']}
    save(fig, 'timeline_AB',
         f'同一冻结历史方案（{d["case"]}，{d["k"]} 核，机理对照而非当前最优成绩）在两种场景下的逐核执行时间线。每核上条为计算流水线，下条为搬运流水线。'
         f'场景A 中每个子图独立成 Task，跨子图数据全部经 DDR 往返，makespan {d["A"]["makespan"]:,}；'
         f'场景B 同核子图合并，搬运明显减少，makespan {d["B"]["makespan"]:,}。')


def f_algos(D):
    best = collections.defaultdict(dict)                  # (p,k,algo) -> case -> 最小 makespan（纯算法，不少用核）
    for r in D['pf']:
        if r['algo'] not in ('lpt', 'band', 'phase') or (r.get('keff') or r['k']) != r['k']:
            continue
        key = (r['problem'], r['k'], r['algo'])
        if r['case'] not in best[key] or r['makespan'] < best[key][r['case']]:
            best[key][r['case']] = r['makespan']
    fig, axes = plt.subplots(1, 2, figsize=(FULL, 2.6), sharey=True)
    ks = [1, 2, 3, 4, 5]
    fin = {}
    for ax, p, tt in ((axes[0], 1, '(a) 问题1 · 场景A'), (axes[1], 2, '(b) 问题2 · 场景B')):
        for algo, col, mk, lab in (('lpt', C1, 'o', '分量装箱'), ('band', C2, 's', '层带划分'), ('phase', C3, 'D', '相位构造')):
            ys = [1.0] + [st.mean(D['sc'][c] / m for c, m in best[(p, k, algo)].items()) for k in ks[1:]]
            ax.plot(ks, ys, color=col, marker=mk, linewidth=1.2, label=lab)
            fin[(p, algo)] = ys[-1]
        port = [st.mean(sp(D, p, k, c) for c in D['cases']) for k in ks]
        ax.plot(ks, port, color=INK, marker='*', markersize=7, linewidth=1.8, label='逐用例选优')
        fin[(p, 'port')] = port[-1]
        end_label(ax, 5, port[-1], f'{port[-1]:.2f}', dy=6)
        ax.set_xticks(ks); ax.set_xlabel('核数'); ax.set_title(tt); ax.set_xlim(0.8, 5.5)
    axes[0].set_ylabel('平均加速比'); axes[0].legend(loc='upper left')
    save(fig, 'algo_compare',
         f'三类构造算法与逐用例选优的平均加速比。任一单一算法都明显落后于逐用例选优：5 核时问题2 中分量装箱、层带划分、'
         f'相位构造分别为 {fin[(2,"lpt")]:.2f}、{fin[(2,"band")]:.2f}、{fin[(2,"phase")]:.2f}，逐用例选优为 {fin[(2,"port")]:.2f}。')


def f_wins(D):
    fig, axes = plt.subplots(1, 2, figsize=(FULL, 2.55), sharey=True)
    algos = (('lpt', C1, '分量装箱', ''), ('band', C2, '层带划分', ''),
             ('phase', C3, '相位构造', ''), ('localsearch', NEUTRAL, '局部搜索', ''),
             ('coarsen', C1, '成组合并', '///'), ('crosseval', C2, '交叉复评', 'xx'),
             ('monotone', C3, '核数补齐', '...'))
    for ax, p, tt in ((axes[0], 1, '(a) 问题1 · 4核'), (axes[1], 2, '(b) 问题2 · 4核')):
        cnt = collections.defaultdict(collections.Counter)
        for c in D['cases']:
            e = D['ev'].get(f'p{p}_k4_{c}')
            if not e:
                continue
            s = e['source']
            label = s['algo'] if s['src'] == 'sweep' else s['src']
            if label not in {a[0] for a in algos}:
                raise ValueError(f'unknown winner source: {label}')
            cnt[family(D, c)][label] += 1
        fams = ['I', 'II', 'III']
        bottom = [0] * 3
        for algo, col, lab, hatch in algos:
            v = [cnt[f][algo] / max(sum(cnt[f].values()), 1) * 100 for f in fams]
            if not any(v):
                continue
            ax.bar(range(3), v, bottom=bottom, color=col, width=0.6, label=lab,
                   edgecolor='white', linewidth=1.0, hatch=hatch)
            for i, (b0, x) in enumerate(zip(bottom, v)):
                if x >= 9:
                    ax.text(i, b0 + x / 2, f'{x:.0f}%', ha='center', va='center', fontsize=7.2,
                            color='white' if col in (C1,) else INK)
            bottom = [b0 + x for b0, x in zip(bottom, v)]
        ax.set_xticks(range(3)); ax.set_xticklabels([f'{FAML[f]}\n({sum(cnt[f].values())} 例)' for f in fams])
        ax.set_title(tt); ax.set_ylim(0, 100)
    axes[0].set_ylabel('最优方案来源占比 (%)')
    axes[1].legend(loc='upper left', bbox_to_anchor=(1.0, 1.0))
    save(fig, 'algo_wins', '各结构族中最终选中方案的记录来源（4 核）。成组合并和交叉复评单独统计，不归入局部搜索；'
         '它们表示后处理或复评来源，不等同于底层构造算法。')


def f_heat(D):
    order = sorted(D['cases'], key=lambda c: ({'I': 0, 'II': 1, 'III': 2}[family(D, c)],
                                               D['ch'][c]['cyc_M'] + D['ch'][c]['cyc_V']))
    fig, axes = plt.subplots(2, 1, figsize=(FULL, 2.6), sharex=True)
    vmax = 5.0
    for ax, p, tt in ((axes[0], 1, '(a) 问题1'), (axes[1], 2, '(b) 问题2')):
        M = [[(sp(D, p, k, c) or 0) for c in order] for k in (2, 3, 4, 5)]
        im = ax.imshow(M, aspect='auto', cmap=BLUES, vmin=1, vmax=vmax, interpolation='nearest')
        ax.set_yticks(range(4)); ax.set_yticklabels(['2核', '3核', '4核', '5核']); ax.grid(False)
        ax.set_title(tt)
        bounds = [0]
        for f in ('I', 'II'):
            bounds.append(bounds[-1] + sum(family(D, c) == f for c in order))
        for b in bounds[1:]:
            ax.axvline(b - 0.5, color='white', linewidth=1.5)
    cen = [(bounds[0] + bounds[1]) / 2 - 0.5, (bounds[1] + bounds[2]) / 2 - 0.5, (bounds[2] + len(order)) / 2 - 0.5]
    axes[1].set_xticks(cen); axes[1].set_xticklabels([FAML[f] for f in ('I', 'II', 'III')])
    axes[1].tick_params(axis='x', length=0); axes[0].tick_params(axis='x', length=0)
    axes[1].set_xlabel('用例（按结构族分组，组内按规模从小到大）')
    cb = fig.colorbar(im, ax=axes, fraction=0.025, pad=0.01)
    cb.set_label('加速比'); cb.outline.set_linewidth(0.5)
    save(fig, 'speedup_heatmap', '逐用例加速比热力图（相对官方单核基准）。颜色越深加速比越高；单一巨块族中的小规模用例是主要短板。')


def f_speedup(D):
    fig, axes = plt.subplots(1, 2, figsize=(FULL, 2.7), sharey=True)
    ks = [1, 2, 3, 4, 5]
    res = {}
    for ax, p, tt, col, mk in ((axes[0], 1, '(a) 问题1 · 场景A', C1, 'o'), (axes[1], 2, '(b) 问题2 · 场景B', C2, 's')):
        per = {k: [sp(D, p, k, c) for c in D['cases'] if sp(D, p, k, c)] for k in ks}
        mean = [st.mean(per[k]) for k in ks]
        rf = [st.mean(ref(D, p, k, c) for c in D['cases'] if ref(D, p, k, c)) for k in ks]
        for k in ks[1:]:
            ax.scatter([k] * len(per[k]), per[k], s=4, color=col, alpha=0.18, linewidths=0, zorder=1)
        ax.plot(ks, ks, color=REF, linewidth=0.8, zorder=2)
        ax.plot(ks, rf, color=INK2, linewidth=1.0, marker='^', markersize=3.8, zorder=3)
        ax.plot(ks, mean, color=col, marker=mk, zorder=4, linewidth=1.8)
        end_label(ax, 5, mean[-1], f'本文 {mean[-1]:.2f}', dy=-1)
        end_label(ax, 5, rf[-1], f'可达参考 {rf[-1]:.2f}', dy=1)
        ax.text(4.35, 4.62, '线性', color=REF, fontsize=7.5, rotation=34, ha='center')
        ax.set_title(tt); ax.set_xticks(ks); ax.set_xlabel('核数'); ax.set_xlim(0.8, 6.0)
        res[p] = (mean, rf)
    axes[0].set_ylabel('平均加速比'); axes[0].set_ylim(0, 6.2)
    m1, m2 = res[1][0], res[2][0]
    save(fig, 'speedup_p12',
         '1–5 核平均加速比（相对官方单核基准，100 个用例算术平均；1 核按题目定义为 1）。淡色点为逐用例加速比，'
         '三角为含跨核同步代价的可达参考。问题1：' + '、'.join(f'{v:.2f}' for v in m1) +
         '；问题2：' + '、'.join(f'{v:.2f}' for v in m2) + '。少数用例超过线性，是因为官方单核基准本身存在大量换入换出。')


def f_p3(D):
    ev, sc, cases, ks = D['ev'], D['sc'], D['cases'], [1, 2, 3, 4, 5]
    no = [st.mean(sc[c] / ev[f'p2_k{k}_{c}']['makespan'] for c in cases) for k in ks]
    ca = [st.mean(sc[c] / ev[f'p3_k{k}_{c}']['makespan'] for c in cases) for k in ks]
    best = [st.mean(ev[f'p2_k{k}_{c}']['makespan'] / ev[f'p3_k{k}_{c}']['makespan'] for c in cases) for k in ks]
    same = [st.mean(ev[f'p2x_k{k}_{c}']['makespan'] / ev[f'p3_k{k}_{c}']['makespan'] for c in cases) for k in ks]
    mx = [max(ev[f'p2_k{k}_{c}']['makespan'] / ev[f'p3_k{k}_{c}']['makespan'] for c in cases) for k in ks]
    hr = [st.mean(ev[f'p3_k{k}_{c}']['cache']['hit_rate'] for c in cases) * 100 for k in ks]
    fig, (a, b) = plt.subplots(1, 2, figsize=(FULL, 2.55))
    fig.subplots_adjust(wspace=0.42)
    a.plot(ks, no, color=C1, marker='o'); a.plot(ks, ca, color=C2, marker='s')
    end_label(a, 5, no[-1], f'无L2 {no[-1]:.2f}', dy=-5); end_label(a, 5, ca[-1], f'只读Cache {ca[-1]:.2f}', dy=5)
    a.set_title('(a) 相对官方单核基准', pad=12); a.set_ylabel('平均加速比')
    a.set_xticks(ks); a.set_xlabel('核数'); a.set_xlim(0.8, 6.4); a.set_ylim(0, 4.6)
    b.plot(ks, best, color=C2, marker='s'); b.plot(ks, same, color=C3, marker='D')
    b.axhline(1.0, color=REF, linewidth=0.8)
    end_label(b, 5, best[-1], f'各自最优 {best[-1]:.3f}', dy=-5); end_label(b, 5, same[-1], f'同一方案 {same[-1]:.3f}', dy=5)
    ymax = max(1.072, max(best + same) + 0.025)
    for k, m in zip(ks, mx):
        b.text(k, ymax - 0.006, f'{m:.2f}', fontsize=7, color=INK2, ha='center', va='center')
    b.text(5.45, ymax - 0.006, '← 单例最大', fontsize=7, color=INK2, ha='left', va='center')
    b.set_title('(b) 无L2 / 只读Cache', pad=12); b.set_ylabel('makespan 之比')
    b.set_xticks(ks); b.set_xlabel('核数'); b.set_xlim(0.7, 6.4)
    b.set_ylim(min(0.99, min(best + same) - 0.01), ymax)
    FIGNUM['p3'] = {'best': best, 'same': same, 'max': mx, 'hit_pct': hr, 'noL2': no, 'cache': ca}
    save(fig, 'p3_compare',
         '无L2 与只读Cache 两种配置的对比。(a) 两种配置各自逐用例选优后的平均加速比；(b) 同核数下 Cache 相对无L2 的'
         '加速比 T无L2/TCache（「各自最优」为两种配置分别取最优方案，「同一方案」为问题3 所选方案放回无L2 复评），图顶为单个用例的最大值。'
         '5 核时平均加速比 ' + f'{best[-1]:.4f}，单例最高 {mx[-1]:.2f}；平均命中率 1–5 核依次为 ' +
         '、'.join(f'{h:.1f}%' for h in hr) + '。')


def f_ddr(D):
    P = pairs(D, 2, 3)
    pts = [(a['sched_bytes'] / 60 / a['makespan'], a['makespan'] / b['makespan']) for a, b in P]
    bins = [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 99)]
    labs = ['0~20%', '20~40%', '40~60%', '60~80%', '≥80%']
    mean = [st.mean(r for d, r in pts if lo <= d < hi) for lo, hi in bins]
    n = [sum(lo <= d < hi for d, _ in pts) for lo, hi in bins]
    fig, ax = plt.subplots(figsize=(HALF, 2.3))
    ax.bar(range(5), [m - 1 for m in mean], bottom=1, color=C1, width=0.62)
    for i, (m, c) in enumerate(zip(mean, n)):
        ax.annotate(f'{m:.3f}', (i, m), xytext=(0, 2.5), textcoords='offset points', ha='center', fontsize=7.2)
    ax.set_xticks(range(5)); ax.set_xticklabels(labs, fontsize=7.2); ax.set_ylim(0.995, 1.105)
    ax.set_xlabel('无L2 时 DDR 忙碌占比'); ax.set_ylabel('无L2 / 只读Cache')
    FIGNUM['ddr'] = {'mean': mean, 'n': n, 'pairs': len(pts)}
    save(fig, 'cache_vs_ddr',
         f'同一方案的缓存收益随 DDR 负载上升（{len(pts)} 组配对）。各组配对数依次为 {"、".join(map(str, n))}。'
         f'DDR 不是瓶颈时命中省下的带宽换不来时间。')


def f_miss(D):
    rows = json.load(open(CACHE_DIAG))
    if len(rows) != len(D['cases']) or {r['case'] for r in rows} != set(D['cases']):
        raise ValueError('incomplete cache diagnostic cases')
    for r in rows:
        e = D['ev'][f'p3_k4_{r["case"]}']
        if r.get('err') or r.get('plan_sha256') != e.get('plan_sha256') or r.get('makespan') != e['makespan']:
            raise ValueError(f'stale cache diagnostic: {r["case"]}')
    sh = lambda r, x: r['bytes'].get(x, 0) / (sum(r['bytes'].values()) or 1) * 100
    rows.sort(key=lambda r: (-sh(r, 'concurrent'), -sh(r, 'hit')))
    cats = (('hit', C3, '命中'), ('concurrent', C2, '并发缺失'), ('capacity', C1, '容量缺失'), ('compulsory', NEUTRAL, '首次缺失'))
    fig, ax = plt.subplots(figsize=(FULL, 2.2))
    bottom = [0] * len(rows)
    means = {}
    for key, col, lab in cats:
        v = [sh(r, key) for r in rows]
        means[key] = st.mean(v)
        ax.bar(range(len(rows)), v, bottom=bottom, color=col, width=0.86, label=f'{lab}（均值 {means[key]:.1f}%）', linewidth=0)
        bottom = [b + x for b, x in zip(bottom, v)]
    ax.set_xlim(-0.8, len(rows) - 0.2); ax.set_ylim(0, 100); ax.set_xticks([])
    ax.set_xlabel('用例（按并发缺失占比从高到低排列）'); ax.set_ylabel('缓存访问字节占比 (%)')
    ax.legend(loc='lower center', ncol=2, bbox_to_anchor=(0.5, 1.0), columnspacing=2.5); ax.grid(False)
    FIGNUM['miss'] = dict(means)
    save(fig, 'miss_breakdown',
         f'缓存访问的缺失分解（4 核，问题3 最优方案，100 个用例）。首次缺失（{means["compulsory"]:.1f}%）缓存无能为力；'
         f'容量缺失占 {means["capacity"]:.1f}%；并发缺失（{means["concurrent"]:.1f}%）是多个核几乎同时读取同一张量、'
         f'前一次读取尚未写入缓存所致，是可以通过调度争取的部分。')


def f_lockstep(D):
    d = json.load(open(os.path.join(ROOT, 'runs/fig_data/lockstep.json')))
    cnt = collections.Counter()
    for bw in ('250', '60'):
        for c, s, e, ev, t in d[bw]['reads']:
            cnt[(bw, t)] += 1
    fig, axes = plt.subplots(2, 1, figsize=(FULL, 2.9), sharex=True)
    k = d['k']
    for ax, bw, tt in ((axes[0], '250', '(a) 官方缓存带宽 250 B/cycle'), (axes[1], '60', '(b) 缓存带宽降为 60 B/cycle（仅作机理验证）')):
        for c, s, e, ev, t in d[bw]['reads']:
            if cnt[(bw, t)] < 2:
                continue
            ax.broken_barh([(s, max(e - s, 1))], (k - 1 - c + 0.15, 0.7), facecolors=C3 if ev == 'hit' else C2,
                           edgecolors='white', linewidth=0.6)
        ms, hr = d[bw]['makespan'], d[bw]['hit_rate']
        ax.axvline(ms, color=INK, linewidth=0.8)
        ax.annotate(f'makespan {ms:,}\n命中率 {hr*100:.1f}%', (ms, k - 0.05), xytext=(4, 0), textcoords='offset points',
                    fontsize=7.4, va='top')
        ax.set_yticks([k - 1 - c + 0.5 for c in range(k)]); ax.set_yticklabels([f'核{c}' for c in range(k)])
        ax.set_ylim(0, k); ax.set_title(tt); ax.grid(False)
    axes[1].set_xlabel('时间（周期）')
    handles = [plt.Rectangle((0, 0), 1, 1, color=C2, label='未命中，从 DDR 读'),
               plt.Rectangle((0, 0), 1, 1, color=C3, label='命中，从缓存读')]
    axes[0].legend(handles=handles, loc='upper right', ncol=2, bbox_to_anchor=(1, 1.35))
    FIGNUM['lockstep'] = {'case': d['case'], 'k': k, 'hit250_pct': d['250']['hit_rate'] * 100, 'hit60_pct': d['60']['hit_rate'] * 100,
                          'ms250': d['250']['makespan'], 'ms60': d['60']['makespan']}
    save(fig, 'lockstep',
         f'锁步读取的历史机理对照（{d["case"]}，{k} 核，同一冻结方案，并非当前最优方案，只显示被多个核读取的张量）。'
         f'(a) 官方配置下存在各核近同时读取、缓存尚未填入而共同缺失的区间；(b) 调低缓存带宽后观察到命中率变化，'
         f'命中率从 {d["250"]["hit_rate"]*100:.1f}% 升至 {d["60"]["hit_rate"]*100:.1f}%，makespan 从 '
         f'{d["250"]["makespan"]:,} 变为 {d["60"]["makespan"]:,}。这是该冻结方案的时序证据，不代表全部用例，也不是修改官方提交配置。')


def f_sens(D):
    R = collections.defaultdict(dict)
    for f in glob.glob(os.path.join(ROOT, 'runs/sens/case_*.json')):
        r = json.load(open(f))
        if 'err' not in r:
            R[(r['case'], r['k'])][(r['kind'], r['val'])] = r
    caps = [262144, 524288, 1048576, 2097152, 4194304, 16777216, 1073741824]
    capl = ['256K', '512K', '1M', '2M', '4M', '16M', '∞']
    bws = [30, 60, 125, 250, 500, 1000]
    fig, ax = plt.subplots(2, 2, figsize=(FULL, 3.7), sharey='row')
    summ = {}
    for k, col, mk in ((4, C1, 'o'), (5, C2, 's')):
        keys = [x for x in R if x[1] == k]
        base = {x: R[x][('cap', 1048576)]['makespan'] for x in keys}
        for j, (kind, vals) in enumerate((('cap', caps), ('bw', bws))):
            ms = [st.mean(R[x][(kind, v)]['makespan'] / base[x] for x in keys) for v in vals]
            hr = [st.mean(R[x][(kind, v)]['hit_rate'] for x in keys) * 100 for v in vals]
            ax[0][j].plot(range(len(vals)), ms, color=col, marker=mk, label=f'{k} 核')
            ax[1][j].plot(range(len(vals)), hr, color=col, marker=mk, label=f'{k} 核')
            summ[(k, kind)] = (ms, hr)
    for j, (vals, lab, off) in enumerate(((caps, capl, 2), (bws, [str(b) for b in bws], 3))):
        for i in (0, 1):
            ax[i][j].set_xticks(range(len(vals))); ax[i][j].set_xticklabels(lab)
            ax[i][j].axvline(off, color=REF, linewidth=0.8)
        ax[0][j].axhline(1.0, color=REF, linewidth=0.8)
        ax[1][j].set_xlabel('缓存容量' if j == 0 else '缓存带宽 (B/cycle)')
    ax[0][0].set_title('(a) 容量（带宽固定 250）'); ax[0][1].set_title('(b) 带宽（容量固定 1M）')
    ax[0][0].set_ylabel('相对 makespan'); ax[1][0].set_ylabel('平均命中率 (%)')
    ax[0][0].legend(loc='upper right')
    fig.tight_layout(h_pad=0.8)
    m4c, h4c = summ[(4, 'cap')]
    FIGNUM['sens'] = {f'k{kk}_{kind}_ms': v[0] for (kk, kind), v in summ.items()}
    FIGNUM['sens'].update({f'k{kk}_{kind}_hit': v[1] for (kk, kind), v in summ.items()})
    save(fig, 'cache_sensitivity',
         f'缓存容量与带宽的历史敏感性实验（固定前期扫描阶段选出的方案，只改缓存参数重评，100 个用例；竖线为官方配置；未重跑当前后处理方案）。'
         f'4 核时容量从 256K 增至无限，平均 makespan 由 {m4c[0]:.3f} 降至 {m4c[-1]:.3f}，命中率由 {h4c[0]:.0f}% 升至 {h4c[-1]:.0f}%；'
         f'该批固定方案在带宽高于 250 后平均变化很小；不能推广为所有方案均已饱和。')


FIGS = [f_dataset, f_bounds, f_size, f_traffic, f_spill, f_timeline, f_algos, f_wins, f_speedup, f_heat,
        f_p3, f_ddr, f_miss, f_lockstep, f_sens]

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('figures', nargs='*')
    ap.add_argument('--deliverables')
    ap.add_argument('--cache-diag', default=CACHE_DIAG)
    ap.add_argument('--out', default=OUT)
    args = ap.parse_args()
    OUT, CACHE_DIAG = os.path.abspath(args.out), os.path.abspath(args.cache_diag)
    os.makedirs(OUT, exist_ok=True)
    want = set(args.figures)
    D = load(args.deliverables)
    print(f'数据: 用例 {len(D["cases"])}，复评 {len(D["ev"])}，扫描 {len(D["pf"])}')
    for f in FIGS:
        if not want or f.__name__[2:] in want:
            f(D)
    capf = os.path.join(OUT, 'captions.md')
    old = {}
    if os.path.exists(capf) and want:
        for blk in open(capf).read().split('\n## ')[1:]:
            n, _, t = blk.partition('\n')
            old[n.strip()] = t.strip()
    old.update(CAP)
    with open(capf, 'w') as fh:
        fh.write('# 图注草稿（由 src/make_figures.py 自动生成，数字与图一致）\n')
        for n, t in old.items():
            fh.write(f'\n## {n}\n{t}\n')
    print('图注 →', capf)
    fnf = os.path.join(OUT, 'fig_numbers.json')
    oldn = json.load(open(fnf)) if (os.path.exists(fnf) and want) else {}
    oldn.update(FIGNUM)
    json.dump(oldn, open(fnf, 'w'), ensure_ascii=False, indent=1)
    print('图中数字 →', fnf)
