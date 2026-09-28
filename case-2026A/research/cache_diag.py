# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
# 人工智能工具：OpenAI Codex（ChatGPT 桌面应用），版本/型号：【待团队按会话记录填写】，开发机构：OpenAI，版本发布日期：【待填写】
"""问题3 缓存诊断：命中率低，是没有重复读（首次缺失）还是重复读被 FIFO 挤掉了（容量缺失）？

对给定用例/核数，取当前问题3最优方案，跑官方评估器拿完整 cache_events，统计：
  compulsory  首次缺失：该逻辑张量此前从未进过缓存 → 缓存帮不上
  capacity    容量缺失：此前进过缓存但已被 FIFO 淘汰 → 改调度顺序可救
  concurrent  并发缺失：此前读过但还没完成写入（两核几乎同时读）→ 错开时间可救
  hit         命中
并给出 DDR 忙碌占比 = DDR 字节/60/makespan（DDR 不是瓶颈时，命中省下的带宽换不来时间）。
"""
import json, os, sys, subprocess, tempfile, collections, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from finalize import load_candidates, build, ROOT, CFG, PY, plan_hash, atomic_json, read_json


def diag(case, k, deliverables=None):
    if deliverables:
        frozen = read_json(os.path.join(deliverables, 'evals', f'p3_k{k}_{case}.json'))
        plan = read_json(os.path.join(deliverables, 'plans', f'p3_k{k}_{case}.json'))
        if plan_hash(plan) != frozen.get('plan_sha256'):
            raise ValueError('frozen deliverable plan hash mismatch')
        c = frozen['source']
    else:
        cand = load_candidates().get((3, case, k))
        if not cand:
            return None
        c = min(cand, key=lambda x: x['makespan'])
        g = read_json(os.path.join(ROOT, 'pkg', 'data', case + '.json'))
        plan = build(g, k, c)
    with tempfile.TemporaryDirectory() as td:
        pp = os.path.join(td, 'p.json'); json.dump(plan, open(pp, 'w'))
        subprocess.run([PY, os.path.join(ROOT, 'pkg/code/multicore_cut_evaluate_problem_3.py'),
                        os.path.join(ROOT, 'pkg/data', case + '.json'), pp, '--config', CFG,
                        '-o', td + '/r.json', '--trace-output', td + '/t.json', '--log-output', td + '/l.txt'],
                       capture_output=True, check=True)
        r = json.load(open(td + '/r.json'))
    if r['makespan'] != c['makespan']:
        raise ValueError('diagnostic evaluation disagrees with selected makespan')
    ev = sorted(r['cache_events'], key=lambda e: e['time'])
    inserted, started = set(), set()
    cnt, byt = collections.Counter(), collections.Counter()
    size = {}
    for e in ev:
        t = e['tensor_id']
        if e['event'] == 'insert':
            inserted.add(t); size[t] = e['size_bytes']
            continue
        b = e.get('size_bytes') or e.get('bytes') or size.get(t, 0)
        if e['event'] == 'hit':
            kind = 'hit'
        elif t in inserted:
            kind = 'capacity'
        elif t in started:
            kind = 'concurrent'
        else:
            kind = 'compulsory'
        started.add(t)
        cnt[kind] += 1; byt[kind] += b
    dm = r['data_movement_bytes']
    # 问题3 结果没有 physical_ddr_bytes 字段；旧代码退回 scheduled_copy_bytes，把缓存命中也算成了 DDR
    # （case_080 因此算出 114%）。按 Codex 评审修正：实际 DDR 字节 = 调度搬运字节 − 命中字节。
    ddr = dm['scheduled_copy_bytes'] - (r.get('cache_stats') or {}).get('hit_bytes', 0)
    return {'case': case, 'k': k, 'makespan': r['makespan'], 'src': c.get('algo', c['src']),
            'hit_rate': r['cache_stats']['hit_rate'], 'cnt': dict(cnt),
            'source': c, 'plan_sha256': plan_hash(plan), 'bytes': dict(byt), 'ddr_bytes': ddr,
            'bytes_MB': {x: round(v / 1e6, 2) for x, v in byt.items()},
            'ddr_busy': round(ddr / 60 / r['makespan'], 3)}


def _safe(args):
    case, k, deliverables = args
    try:
        return diag(case, k, deliverables)
    except Exception as e:
        return {'case': case, 'err': str(e)[:120]}


def survey(k, jobs=10, deliverables=None, output=None):
    """全部用例诊断 → runs/cache_diag_k{k}.json，并估算"错开读取"的潜力。"""
    import glob, statistics as st
    from concurrent.futures import ProcessPoolExecutor
    cases = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(ROOT, 'pkg/data/case_[0-9][0-9][0-9].json')))
    with ProcessPoolExecutor(jobs) as ex:
        rows = [r for r in ex.map(_safe, [(c, k, deliverables) for c in cases]) if r]
    dest = output or os.path.join(ROOT, f'runs/cache_diag_k{k}.json')
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    atomic_json(dest, rows)
    ok = [r for r in rows if 'err' not in r]
    sh = lambda r, x: r['bytes'].get(x, 0) / (sum(r['bytes'].values()) or 1)
    print(f"诊断完成 {len(ok)}/{len(cases)}")
    if len(ok) != len(cases):
        raise RuntimeError('incomplete diagnostic survey; do not publish figures')
    m = {x: st.mean(sh(r, x) for r in ok) * 100 for x in ('hit', 'concurrent', 'capacity', 'compulsory')}
    print("字节占比均值：" + "  ".join(f"{x} {v:.1f}%" for x, v in m.items()))
    print(f"容量缺失 >1% 的用例: {sum(sh(r,'capacity') > 0.01 for r in ok)}")
    pot = sorted(((sh(r, 'concurrent') * r['ddr_busy'], r) for r in ok), key=lambda x: -x[0])
    print(f"并发缺失×DDR忙碌指标 >5%: {sum(p > .05 for p, _ in pot)} 个；>2%: {sum(p > .02 for p, _ in pot)} 个（不是可达收益或上界）")
    for p, r in pot[:10]:
        print(f"  {r['case']} 指标={p*100:.1f}%  并发缺失 {sh(r,'concurrent')*100:.0f}%  "
              f"DDR忙碌 {r['ddr_busy']*100:.0f}%  命中率 {r['hit_rate']*100:.0f}%  [{r['src']}]")


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--survey', type=int, metavar='K')
    ap.add_argument('--jobs', type=int, default=10)
    ap.add_argument('--deliverables', help='使用已复评且带方案哈希的冻结交付目录')
    ap.add_argument('--output')
    ap.add_argument('k', nargs='?', type=int)
    ap.add_argument('cases', nargs='*')
    args = ap.parse_args()
    directory = os.path.abspath(args.deliverables) if args.deliverables else None
    if args.survey is not None:
        survey(args.survey, args.jobs, directory, args.output); sys.exit()
    if args.k is None:
        ap.error('specify K or --survey K')
    k = args.k
    for case in args.cases:
        d = diag(case, k, directory)
        if not d:
            print(case, '无候选'); continue
        tot = sum(d['bytes_MB'].values()) or 1
        share = {x: f"{v/tot*100:.0f}%" for x, v in d['bytes_MB'].items()}
        print(f"{case} k{k} [{d['src']}] makespan={d['makespan']:,} 命中率={d['hit_rate']*100:.1f}% "
              f"DDR忙碌={d['ddr_busy']*100:.0f}%  字节占比 {share}")
