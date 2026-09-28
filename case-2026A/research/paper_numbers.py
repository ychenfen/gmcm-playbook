# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方公布为准）
"""论文正文引用的全部统计量，从已验收的 deliverables/ 与扫描记录 runs/ 计算，写入 paper/numbers.json。

只读，不调用评估器。正文里出现的数字都应能在 numbers.json 中找到对应条目（键名即出处说明）。
用法: python3 src/paper_numbers.py
"""
import json, os, glob, csv, collections, statistics as st

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
D = os.path.join(ROOT, 'deliverables')
R = os.path.join(ROOT, 'runs')
OUT = os.path.join(ROOT, 'paper', 'numbers.json')
KS = (2, 3, 4, 5)


def mean(v):
    v = list(v)
    return sum(v) / len(v) if v else float('nan')


def rows(path):
    return list(csv.DictReader(open(path, encoding='utf-8')))


def family(frac):
    return 'I' if frac > 0.8 else ('II' if frac >= 0.3 else 'III')


def main():
    N = {}
    conn = {r['case']: r for r in json.load(open(os.path.join(R, 'connectivity.json')))}
    char = {r['case']: r for r in json.load(open(os.path.join(R, 'characterize.json')))}
    fam = {c: family(r['top_comp_frac_cyc']) for c, r in conn.items()}
    N['family_count'] = dict(collections.Counter(fam.values()))
    sync = collections.defaultdict(dict)
    for r in json.load(open(os.path.join(R, 'ideal_sync.json'))):
        sync[r['sync']][r['case']] = r
    ideal = {r['case']: r for r in json.load(open(os.path.join(R, 'ideal_bound.json')))}

    # ---------- 最终交付（问题1/2）
    single = {}
    final = {1: {}, 2: {}}
    added = {1: {}, 2: {}}
    for p in (1, 2):
        for r in rows(os.path.join(D, f'appendix_p{p}.csv')):
            c = r['case']
            single[c] = int(r['singlecore_makespan'])
            for k in KS:
                final[p][(c, k)] = float(r[f'speedup_k{k}'])
                added[p][(c, k)] = int(r[f'added_bytes_k{k}'])
    cases = sorted(single)
    N['n_cases'] = len(cases)
    for p in (1, 2):
        for k in KS:
            N[f'p{p}_k{k}_final_mean'] = mean(final[p][(c, k)] for c in cases)
            N[f'p{p}_k{k}_final_min'] = min(final[p][(c, k)] for c in cases)
            N[f'p{p}_k{k}_final_max'] = max(final[p][(c, k)] for c in cases)
            N[f'p{p}_k{k}_added_MB_mean'] = mean(added[p][(c, k)] for c in cases) / 1e6
            N[f'p{p}_k{k}_eff_mean'] = N[f'p{p}_k{k}_final_mean'] / k      # 平均并行效率
            for f in ('I', 'II', 'III'):
                cs = [c for c in cases if fam[c] == f]
                N[f'p{p}_k{k}_fam{f}_mean'] = mean(final[p][(c, k)] for c in cs)
            # 含同步代价的可达参考（问题1 1000、问题2 500 周期）
            s = 1000.0 if p == 1 else 500.0
            ach = [final[p][(c, k)] / (single[c] / sync[s][c][f'k{k}']) for c in cases]
            N[f'p{p}_k{k}_ref_speedup_mean'] = mean(single[c] / sync[s][c][f'k{k}'] for c in cases)
            N[f'p{p}_k{k}_achieve_mean'] = mean(ach)
            N[f'p{p}_k{k}_above_ref'] = sum(1 for a in ach if a > 1)
            for f in ('I', 'II', 'III'):
                N[f'p{p}_k{k}_fam{f}_achieve'] = mean(a for a, c in zip(ach, cases) if fam[c] == f)
            N[f'p{p}_k{k}_ideal0_speedup_mean'] = mean(single[c] / ideal[c][f'ideal_{k}'] for c in cases)
            N[f'p{p}_k{k}_superlinear'] = sum(1 for c in cases if final[p][(c, k)] > k)
        N[f'p{p}_monotone_cases'] = sum(1 for c in cases
                                        if all(final[p][(c, k)] >= final[p][(c, k - 1)] for k in (3, 4, 5))
                                        and final[p][(c, 2)] >= 1)
    # 场景 B 相对场景 A：同一用例、同一核数
    for k in KS:
        rat = [final[1][(c, k)] / final[2][(c, k)] for c in cases]
        N[f'pA_over_B_speedup_k{k}'] = mean(rat)
        N[f'p2_better_k{k}'] = sum(1 for c in cases if final[2][(c, k)] > final[1][(c, k)] * 1.001)
        N[f'p1_better_k{k}'] = sum(1 for c in cases if final[1][(c, k)] > final[2][(c, k)] * 1.001)
        N[f'p1_p2_tie_k{k}'] = len(cases) - N[f'p2_better_k{k}'] - N[f'p1_better_k{k}']
        N[f'added_ratio_B_over_A_k{k}'] = (sum(added[2][(c, k)] for c in cases) /
                                           max(1, sum(added[1][(c, k)] for c in cases)))

    # 场景 A 反而优于场景 B 的用例：换出是否更多（5 核）
    for k in (4, 5):
        ab, ot = [], []
        for c in cases:
            e1 = json.load(open(os.path.join(D, 'evals', f'p1_k{k}_{c}.json')))['data_movement_bytes']
            e2 = json.load(open(os.path.join(D, 'evals', f'p2_k{k}_{c}.json')))['data_movement_bytes']
            more = (e2.get('spill_added_copy_bytes') or 0) > (e1.get('spill_added_copy_bytes') or 0)
            (ab if final[1][(c, k)] > final[2][(c, k)] * 1.001 else ot).append((final[1][(c, k)] / final[2][(c, k)], more))
        N[f'AbeatsB_k{k}_n'] = len(ab)
        N[f'AbeatsB_k{k}_morespill'] = sum(m for _, m in ab)
        N[f'AbeatsB_k{k}_max_pct'] = (max(r for r, _ in ab) - 1) * 100 if ab else 0.0
        N[f'AbeatsB_k{k}_median_pct'] = (st.median(r for r, _ in ab) - 1) * 100 if ab else 0.0
        N[f'others_k{k}_n'] = len(ot)
        N[f'others_k{k}_morespill'] = sum(m for _, m in ot)

    # ---------- 扫描记录：朴素基线与各构造算法
    best = collections.defaultdict(dict)          # (p,c,k) -> {label: makespan}
    for f in glob.glob(os.path.join(R, 'pf', '*.json')):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if 'err' in r or not r.get('makespan'):
            continue
        p, c, k, a = r['problem'], r['case'], r['k'], r['algo']
        if p not in (1, 2, 3) or k not in KS:
            continue
        keff = r.get('keff') or k
        key = (p, c, k)
        m = r['makespan']
        labs = [a, 'portfolio']
        if a == 'lpt' and abs(r['div'] - 0.25) < 1e-9 and keff == k:
            labs.append('naive')
        for L in labs:
            if L not in best[key] or m < best[key][L]:
                best[key][L] = m
    for p in (1, 2):
        for k in KS:
            for L in ('naive', 'lpt', 'band', 'phase', 'portfolio'):
                v = [single[c] / best[(p, c, k)][L] for c in cases if L in best[(p, c, k)]]
                N[f'p{p}_k{k}_{L}_mean'] = mean(v)
                N[f'p{p}_k{k}_{L}_n'] = len(v)
            N[f'p{p}_k{k}_lptband_mean'] = mean(single[c] / min(best[(p, c, k)]['lpt'], best[(p, c, k)]['band'])
                                              for c in cases)
            wins = collections.Counter()
            for c in cases:
                b = best[(p, c, k)]
                cand = {L: b[L] for L in ('lpt', 'band', 'phase') if L in b}
                wins[min(cand, key=cand.get)] += 1
            N[f'p{p}_k{k}_algo_wins'] = dict(wins)
    # 分族 × 算法（各自参数网格上逐用例最优）；相位构造胜出的 λ 分布
    for p in (1, 2):
        for k in (4, 5):
            for f in ('I', 'II', 'III'):
                cs = [c for c in cases if fam[c] == f]
                for L in ('lpt', 'band', 'phase'):
                    N[f'p{p}_k{k}_fam{f}_{L}_mean'] = mean(single[c] / best[(p, c, k)][L] for c in cs)
    lam = collections.defaultdict(dict)
    for f in glob.glob(os.path.join(R, 'pf', '*_phase_*.json')):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if r.get('makespan') and 'err' not in r and r['k'] in KS and r['problem'] in (1, 2):
            key = (r['problem'], r['case'], r['k'])
            if key not in lam or r['makespan'] < lam[key][1]:
                lam[key] = (r['div'], r['makespan'])
    for p in (1, 2):
        v = [lam[(p, c, k)][0] for c in cases for k in KS if (p, c, k) in lam]
        N[f'p{p}_phase_bestlam_median'] = st.median(v)
        N[f'p{p}_phase_bestlam_share_ge50000'] = sum(1 for x in v if x >= 50000) / len(v)
        N[f'p{p}_phase_bestlam_share_le2000'] = sum(1 for x in v if x <= 2000) / len(v)
    # 分族的朴素基线与构造阶段选优
    for p in (1, 2):
        for k in KS:
            for f in ('I', 'II', 'III'):
                cs = [c for c in cases if fam[c] == f]
                for L in ('naive', 'portfolio'):
                    N[f'p{p}_k{k}_fam{f}_{L}_mean'] = mean(single[c] / best[(p, c, k)][L] for c in cs)
    for f in ('I', 'II', 'III'):
        cs = [c for c in cases if fam[c] == f]
        N[f'fam{f}_ops_median'] = st.median(char[c]['n_ops'] for c in cs)
        N[f'fam{f}_width_median'] = st.median(char[c]['cyc_total'] / max(1, char[c]['crit_path']) for c in cs)
        N[f'fam{f}_single_median'] = st.median(single[c] for c in cs)
    # 三层参照：解析界、零通信理想表调度（并行效率）
    for k in (1, 2, 3, 4, 5):
        lb = {c: max(char[c]['crit_path'], char[c]['cyc_M'] / k, char[c]['cyc_V'] / k, char[c]['ddr_lb_cycles'])
              for c in cases}
        N[f'lb_k{k}_speedup_mean'] = mean(single[c] / lb[c] for c in cases)
        N[f'ideal_k{k}_eff_mean'] = mean(ideal[c]['ideal_1'] / (k * ideal[c][f'ideal_{k}']) for c in cases)
        N[f'ideal_k{k}_eff_median'] = st.median(ideal[c]['ideal_1'] / (k * ideal[c][f'ideal_{k}']) for c in cases)
        N[f'ideal_k{k}_eff_lt50'] = sum(1 for c in cases if ideal[c]['ideal_1'] / (k * ideal[c][f'ideal_{k}']) < 0.5)
    # 解析界是否被任何实测结果突破（检验其下界性质）；达成率与规模的相关性
    import math
    for p in (1, 2):
        viol = 0
        for k in KS:
            for c in cases:
                lb = max(char[c]['crit_path'], char[c]['cyc_M'] / k, char[c]['cyc_V'] / k, char[c]['ddr_lb_cycles'])
                if final[p][(c, k)] > single[c] / lb * 1.0000001:
                    viol += 1
        N[f'p{p}_lb_violations'] = viol
        s = 1000.0 if p == 1 else 500.0
        xs = [math.log10(char[c]['cyc_total']) for c in cases]
        ys = [final[p][(c, 4)] / (single[c] / sync[s][c]['k4']) for c in cases]
        mx, my = mean(xs), mean(ys)
        cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        N[f'p{p}_k4_size_corr'] = cov / math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys))
        small = [y for x, y in zip(xs, ys) if x < 5]
        N[f'p{p}_k4_small_n'] = len(small)
        N[f'p{p}_k4_small_achieve_sd'] = st.pstdev(small) if len(small) > 1 else 0.0
        N[f'p{p}_k4_large_achieve_sd'] = st.pstdev([y for x, y in zip(xs, ys) if x >= 6])
    # 由浅入深阶梯：按来源逐层加入候选池后的平均加速比（顺序固定；是累计效果，不是各步的独立贡献）
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from finalize import load_candidates
    cand = load_candidates()
    ladder = [('naive', None), ('sweep', {'sweep'}), ('coarsen', {'sweep', 'coarsen'}),
              ('localsearch', {'sweep', 'coarsen', 'localsearch'}),
              ('crosseval', {'sweep', 'coarsen', 'localsearch', 'crosseval'}),
              ('monotone', {'sweep', 'coarsen', 'localsearch', 'crosseval', 'monotone'})]
    for p in (1, 2, 3):
        for k in KS:
            for name, srcs in ladder:
                v = []
                for c in cases:
                    cs = cand.get((p, c, k), [])
                    if name == 'naive':
                        cs = [x for x in cs if x.get('src') == 'sweep' and x.get('algo') == 'lpt'
                              and abs(x.get('div', 0) - 0.25) < 1e-9 and (x.get('keff') or k) == k]
                    else:
                        cs = [x for x in cs if x.get('src') in srcs]
                    if cs:
                        v.append(single[c] / min(x['makespan'] for x in cs))
                N[f'ladder_p{p}_k{k}_{name}'] = mean(v) if len(v) == len(cases) else float('nan')
    # 典型用例 case_002（单一巨块）：4 核逐级结果
    c0 = 'case_002'
    N['cs_ops'] = char[c0]['n_ops']; N['cs_width'] = char[c0]['cyc_total'] / char[c0]['crit_path']
    N['cs_single'] = single[c0]
    for p in (1, 2):
        cs = cand[(p, c0, 4)]
        levels = {'naive': lambda x: x.get('src') == 'sweep' and x.get('algo') == 'lpt' and abs(x.get('div', 0) - 0.25) < 1e-9,
                  'lpt': lambda x: x.get('src') == 'sweep' and x.get('algo') == 'lpt',
                  'band': lambda x: x.get('src') == 'sweep' and x.get('algo') == 'band',
                  'phase': lambda x: x.get('src') == 'sweep' and x.get('algo') == 'phase',
                  'final': lambda x: True}
        for n_, f_ in levels.items():
            b_ = min((x for x in cs if f_(x)), key=lambda x: x['makespan'])
            N[f'cs_p{p}_{n_}_ms'] = b_['makespan']; N[f'cs_p{p}_{n_}_sp'] = single[c0] / b_['makespan']
            if b_.get('src') == 'sweep':
                N[f'cs_p{p}_{n_}_div'] = b_['div']
        e_ = json.load(open(os.path.join(D, 'evals', f'p{p}_k4_{c0}.json')))
        N[f'cs_p{p}_final_nsg'] = e_['n_subgraphs']
        N[f'cs_p{p}_final_added_MB'] = e_['data_movement_bytes']['added_copy_bytes'] / 1e6
    # 缓存典型用例：case_090（5 核收益最大）与 case_044（锁步示例）
    p3_rows = rows(os.path.join(D, 'appendix_p3.csv'))
    cd_rows = json.load(open(os.path.join(D, 'analysis', 'cache_diag_k4.json')))
    for c1 in ('case_090', 'case_044'):
        for r in p3_rows:
            if r['case'] == c1:
                kk = r['k']
                N[f'cc_{c1}_k{kk}_noL2'] = int(r['noL2_makespan']); N[f'cc_{c1}_k{kk}_cache'] = int(r['cache_makespan'])
                N[f'cc_{c1}_k{kk}_best'] = float(r['cache_speedup_best']); N[f'cc_{c1}_k{kk}_hit'] = float(r['cache_hit_rate'])
                N[f'cc_{c1}_k{kk}_same'] = float(r['cache_speedup_sameplan'])
        for r in cd_rows:
            if r['case'] == c1:
                tot = sum(r['bytes'].values()) or 1
                for kind in ('hit', 'concurrent', 'capacity', 'compulsory'):
                    N[f'cc_{c1}_k4_share_{kind}_pct'] = r['bytes'].get(kind, 0) / tot * 100
                N[f'cc_{c1}_k4_ddrbusy_pct'] = r['ddr_busy'] * 100
    # 成组合并第一轮（runs/co）：相对其起点的缩短比例
    for p in (1, 2, 3):
        red, n_imp = [], 0
        for f in glob.glob(os.path.join(R, 'co', f'case_*_k*_p{p}.json')):
            r = json.load(open(f))
            if r.get('k', 0) < 2 or not r.get('base_makespan') or not r.get('best_makespan'):
                continue
            x = 1 - r['best_makespan'] / r['base_makespan']
            red.append(x); n_imp += x > 0.001
        N[f'co1_p{p}_groups'] = len(red)
        N[f'co1_p{p}_improved'] = n_imp
        N[f'co1_p{p}_mean_red_pct'] = mean(red) * 100
        N[f'co1_p{p}_max_red_pct'] = max(red) * 100
        vv = collections.Counter()
        for f in glob.glob(os.path.join(R, 'co', f'case_*_k*_p{p}.json')):
            r = json.load(open(f))
            if r.get('best_name') and r['best_name'] != 'base':
                vv[r['best_name'].split('_')[1]] += 1
        N[f'co1_p{p}_mode_wins'] = dict(vv)
    red2 = []
    for f in glob.glob(os.path.join(R, 'co2', 'case_*.json')):
        r = json.load(open(f))
        if r.get('base_makespan') and r.get('best_makespan'):
            red2.append(1 - r['best_makespan'] / r['base_makespan'])
    N['co2_groups'] = len(red2); N['co2_mean_red_pct'] = mean(red2) * 100
    # 局部搜索（runs/ls2）：相对起点方案的缩短比例
    pfm = {}
    for f in glob.glob(os.path.join(R, 'pf', '*.json')):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if r.get('makespan') and 'err' not in r:
            pfm[(r['problem'], r['case'], r['k'], r['algo'], float(r['div']), r.get('keff') or r['k'])] = r['makespan']
    lsr, tries, secs = collections.defaultdict(list), [], []
    for f in glob.glob(os.path.join(R, 'ls2', 'case_*.json')):
        r = json.load(open(f))
        if not r.get('makespan') or not r.get('start'):
            continue
        a, dv, ke = r['start']
        m0 = pfm.get((r['problem'], r['case'], r['k'], a, float(dv), ke))
        if m0:
            lsr[r['problem']].append(1 - r['makespan'] / m0)
        tries.append(r.get('tries', 0)); secs.append(r.get('secs', 0))
    for p, v in lsr.items():
        N[f'ls_p{p}_jobs'] = len(v); N[f'ls_p{p}_mean_red_pct'] = mean(v) * 100
        N[f'ls_p{p}_max_red_pct'] = max(v) * 100
        N[f'ls_p{p}_improved'] = sum(1 for x in v if x > 0.001)
    N['ls_tries_median'] = st.median(tries); N['ls_secs_median'] = st.median(secs)
    N['ls_tries_total'] = sum(tries)
    co_ev = sum(len(json.load(open(f))['variants']) + 1 for f in glob.glob(os.path.join(R, 'co*', 'case_*.json')))
    xe_ev = len(glob.glob(os.path.join(R, 'xe', 'case_*.json'))); mono_ev = len(glob.glob(os.path.join(R, 'mono', 'case_*.json')))
    pf_ev = len(glob.glob(os.path.join(R, 'pf', '*.json')))
    N['evals_total'] = pf_ev + co_ev + xe_ev + mono_ev + sum(tries) + 1900
    N['ls_share_pct'] = sum(tries) / N['evals_total'] * 100
    N['co_evals'] = co_ev
    N['ls_jobs_total'] = len(tries)
    # 负面对照（runs/neg，12 例 × 4 核，每族 4 例）：相对同问题 4 核构造阶段选优的 makespan 比
    por4 = {}
    for f in glob.glob(os.path.join(R, 'pf', '*_k4_*.json')):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if r.get('makespan') and r['k'] == 4 and 'err' not in r:
            key = (r['problem'], r['case']); por4[key] = min(por4.get(key, 1 << 62), r['makespan'])
    neg = collections.defaultdict(list)
    for f in glob.glob(os.path.join(R, 'neg', '*.json')):
        r = json.load(open(f))
        if r.get('makespan') and 'err' not in r:
            neg[(r['algo'], r['problem'], r['div'])].append((r['makespan'] / por4[(r['problem'], r['case'])], r['n_subgraphs']))
    for (a, p, dv), v in neg.items():
        tag = f'neg_{a}_p{p}' + (f'_d{int(dv)}' if a == 'phasec' else '')
        N[tag + '_n'] = len(v)
        N[tag + '_geo'] = st.geometric_mean([x[0] for x in v])
        N[tag + '_worst'] = max(x[0] for x in v)
        N[tag + '_nbetter'] = sum(1 for x in v if x[0] < 0.999)
        N[tag + '_nsg_max'] = max(x[1] for x in v)
        N[tag + '_best'] = min(x[0] for x in v)
    # 错开读取后处理的重跑（runs/stagger_rerun_20260924.log）
    import re as _re
    sf = os.path.join(R, 'stagger_rerun_20260924.log')
    if os.path.exists(sf):
        rat = [float(m.group(1)) for m in _re.finditer(r'→ ([\d.]+)x', open(sf, encoding='utf-8').read())]
        N['stagger_n'] = len(rat)
        N['stagger_better'] = sum(1 for x in rat if x > 1.001)
        N['stagger_worse'] = sum(1 for x in rat if x < 0.999)
        N['stagger_same'] = len(rat) - N['stagger_better'] - N['stagger_worse']
        N['stagger_best_pct'] = (max(rat) - 1) * 100
        N['stagger_worst_pct'] = (1 - min(rat)) * 100
    # 构造算法耗时（runs/time_algos.json）与官方评估单次耗时（局部搜索作业 用时/评估次数）
    tf = os.path.join(R, 'time_algos.json')
    if os.path.exists(tf):
        T = json.load(open(tf))
        for a_ in ('lpt', 'band', 'phase'):
            v = [r['secs'] for r in T if r['algo'] == a_]
            N[f'time_{a_}_median'] = st.median(v); N[f'time_{a_}_max'] = max(v)
        big = max(T, key=lambda r: r['n_ops'])
        N['time_bigcase'] = big['case']; N['time_bigcase_ops'] = big['n_ops']
        N['time_all_max'] = max(r['secs'] for r in T)
    per = [json.load(open(f)) for f in glob.glob(os.path.join(R, 'ls2', 'case_*.json'))]
    per = [r['secs'] / r['tries'] for r in per if r.get('tries')]
    N['eval_secs_median'] = st.median(per); N['eval_secs_max'] = max(per); N['eval_secs_min'] = min(per)
    # 参数灵敏度：全量覆盖的参数取值下，各算法 4 核平均加速比
    grid = {'lpt': (0.1, 0.25, 0.5, 1, 2, 4, 8), 'band': (16, 256, 4096), 'phase': (2000, 10000, 50000)}
    val = collections.defaultdict(dict)
    for f in glob.glob(os.path.join(R, 'pf', '*_k4_*.json')):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if r.get('makespan') and 'err' not in r and r['k'] == 4 and r['problem'] in (1, 2) and (r.get('keff') or 4) == 4:
            val[(r['problem'], r['algo'], float(r['div']))][r['case']] = r['makespan']
    for p in (1, 2):
        for a_, g_ in grid.items():
            for dv in g_:
                d = val.get((p, a_, float(dv)), {})
                if len(d) == len(cases):
                    N[f'sens_p{p}_{a_}_{str(dv).replace(".", "p")}'] = mean(single[c] / d[c] for c in cases)
    # 鲁棒性（runs/robust）：各配置下 朴素/本文 的 Makespan 比（几何平均）与本文方案 Makespan 相对官方配置的变化
    rb = collections.defaultdict(dict)
    import hashlib
    cur_hash = {}
    for f in glob.glob(os.path.join(R, 'robust', 'case_*.json')):
        r = json.load(open(f))
        if not r.get('makespan'):
            continue
        if r['plan'] == 'final':                       # 只采用与当前交付方案一致的记录
            key = (r['problem'], r['case'])
            if key not in cur_hash:
                pl = json.load(open(os.path.join(D, 'plans', f"p{r['problem']}_k4_{r['case']}.json")))
                cur_hash[key] = hashlib.sha256(json.dumps(pl, sort_keys=True).encode()).hexdigest()[:12]
            if r.get('plan_hash') != cur_hash[key]:
                continue
        rb[(r['problem'], r['config'])][(r['case'], r['plan'])] = r['makespan']
    for p in (1, 2):
        base = rb.get((p, 'official'), {})
        for cfgn in ('official', 'bw48', 'bw72', 'sync08', 'sync12'):
            d = rb.get((p, cfgn), {})
            cs_ = sorted({c for c, w in d if (c, 'final') in d and (c, 'naive') in d})
            if not cs_:
                continue
            N[f'rob_p{p}_{cfgn}_n'] = len(cs_)
            N[f'rob_p{p}_{cfgn}_adv'] = st.geometric_mean([d[(c, 'naive')] / d[(c, 'final')] for c in cs_])
            N[f'rob_p{p}_{cfgn}_minadv'] = min(d[(c, 'naive')] / d[(c, 'final')] for c in cs_)
            N[f'rob_p{p}_{cfgn}_nworse'] = sum(1 for c in cs_ if d[(c, 'final')] > d[(c, 'naive')])
            cb = [c for c in cs_ if (c, 'final') in base]
            if cb:
                N[f'rob_p{p}_{cfgn}_ms_ratio'] = st.geometric_mean([d[(c, 'final')] / base[(c, 'final')] for c in cb])
    mono = [json.load(open(f)) for f in glob.glob(os.path.join(R, 'mono', 'case_*.json'))]
    for p in (1, 2, 3):
        N[f'mono_p{p}'] = sum(1 for r in mono if r['problem'] == p)
    N['mono_total'] = len(mono)
    N['mono_identical'] = sum(1 for r in mono if r.get('makespan') == r.get('source_makespan_at_from_k'))
    # 扫描评估总数；相对朴素基线的提升
    N['pf_evals'] = len(glob.glob(os.path.join(R, 'pf', '*.json')))
    for p in (1, 2):
        for k in KS:
            N[f'p{p}_k{k}_naive_gain_pct'] = (N[f'p{p}_k{k}_final_mean'] / N[f'p{p}_k{k}_naive_mean'] - 1) * 100
    # 构造阶段逐用例选优 → 最终（后处理贡献）
    for p in (1, 2):
        for k in KS:
            gain = [single[c] / best[(p, c, k)]['portfolio'] for c in cases]
            N[f'p{p}_k{k}_post_gain_pct'] = (N[f'p{p}_k{k}_final_mean'] / mean(gain) - 1) * 100

    # ---------- 最终方案来源与子图数
    src = collections.Counter()
    src_p = collections.defaultdict(collections.Counter)
    for kind, p, c, k, cand in json.load(open(os.path.join(D, 'selected_tasks.json'))):
        if kind != 'main':
            continue
        s = cand.get('algo') if cand.get('src') == 'sweep' else cand.get('src', 'unknown')
        src[s] += 1
        src_p[p][s] += 1
    N['source_mix'] = dict(src)
    N['source_mix_by_problem'] = {str(p): dict(v) for p, v in src_p.items()}
    nsg = collections.defaultdict(list)
    for f in glob.glob(os.path.join(D, 'plans', 'p*_k*_case_*.json')):
        b = os.path.basename(f)[:-5].split('_')
        p, k = int(b[0][1:]), int(b[1][1:])
        pl = json.load(open(f))
        nsg[(p, k)].append(len(set(pl['node_to_subgraph'].values())))
    for (p, k), v in sorted(nsg.items()):
        N[f'p{p}_k{k}_nsg_median'] = st.median(v)
        N[f'p{p}_k{k}_nsg_mean'] = mean(v)

    # ---------- 问题3
    p3 = rows(os.path.join(D, 'appendix_p3.csv'))
    for k in (1, 2, 3, 4, 5):
        rk = [r for r in p3 if int(r['k']) == k]
        b = [float(r['cache_speedup_best']) for r in rk]
        sp = [float(r['cache_speedup_sameplan']) for r in rk]
        h = [float(r['cache_hit_rate']) for r in rk]
        N[f'p3_k{k}_best_mean'] = mean(b)
        N[f'p3_k{k}_best_max'] = max(b)
        N[f'p3_k{k}_best_argmax'] = rk[b.index(max(b))]['case']
        N[f'p3_k{k}_best_min'] = min(b)
        N[f'p3_k{k}_same_mean'] = mean(sp)
        N[f'p3_k{k}_n_gain1pct'] = sum(1 for x in b if x > 1.01)
        N[f'p3_k{k}_n_gain5pct'] = sum(1 for x in b if x > 1.05)
        N[f'p3_k{k}_n_worse'] = sum(1 for x in b if x < 0.999)
        N[f'p3_k{k}_hit_mean'] = mean(h)
        N[f'p3_k{k}_hit_max'] = max(h)
        N[f'p3_k{k}_noL2_added_MB'] = mean(int(r['noL2_added_bytes']) for r in rk) / 1e6
        N[f'p3_k{k}_cache_added_MB'] = mean(int(r['cache_added_bytes']) for r in rk) / 1e6
        N[f'p3_k{k}_noL2_vs_single'] = mean(single[r['case']] / int(r['noL2_makespan']) for r in rk)
        N[f'p3_k{k}_cache_vs_single'] = mean(single[r['case']] / int(r['cache_makespan']) for r in rk)
    worse = [(r['case'], int(r['k']), float(r['cache_speedup_best'])) for r in p3 if float(r['cache_speedup_best']) < 0.999]
    N['p3_worse_total'] = len(worse)
    N['p3_worse_list'] = '、'.join(f"{c}（{k} 核，{x:.3f}）" for c, k, x in sorted(worse, key=lambda t: (t[1], t[0])))
    same_worse = [r for r in p3 if r['cache_speedup_sameplan'] and float(r['cache_speedup_sameplan']) < 0.999]
    N['p3_same_worse_total'] = len(same_worse)
    N['p3_same_min'] = min(float(r['cache_speedup_sameplan']) for r in p3 if r['cache_speedup_sameplan'])
    cd = json.load(open(os.path.join(D, 'analysis', 'cache_diag_k4.json')))
    N['cache_diag_k4_keys'] = sorted(cd.keys())[:20] if isinstance(cd, dict) else type(cd).__name__

    # ---------- 规模
    N['ops_min'] = min(char[c]['n_ops'] for c in cases)
    N['ops_max'] = max(char[c]['n_ops'] for c in cases)
    N['ops_median'] = st.median(char[c]['n_ops'] for c in cases)
    N['width_ratio_median'] = st.median(char[c]['cyc_total'] / max(1, char[c]['crit_path']) for c in cases)
    N['single_min'] = min(single.values()); N['single_max'] = max(single.values())
    N['single_median'] = st.median(single.values())
    N['comp_median'] = st.median(conn[c]['n_comp'] for c in cases)

    json.dump(N, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, sort_keys=True)
    print('写出', OUT, len(N), '项')


if __name__ == '__main__':
    main()
