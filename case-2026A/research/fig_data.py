# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""为时间线类图准备数据（需要官方评估器的完整输出，finalize 只存了摘要）。

输出 runs/fig_data/：
  timeline_AB.json  同一方案（case_010，4 核，问题2最优）分别在场景A、场景B下的每核算子时间线
  lockstep.json     case_044，4 核，问题3最优方案，在官方缓存带宽 250 与 60 下的 COPY_IN 时间线及命中情况
"""
import json, os, sys, subprocess, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from finalize import load_candidates, build, ROOT, CFG, PY

OUT = os.path.join(ROOT, 'runs', 'fig_data')
os.makedirs(OUT, exist_ok=True)


def run(case, plan, problem, cfg=CFG):
    with tempfile.TemporaryDirectory() as td:
        json.dump(plan, open(td + '/p.json', 'w'))
        subprocess.run([PY, os.path.join(ROOT, f'pkg/code/multicore_cut_evaluate_problem_{problem}.py'),
                        os.path.join(ROOT, 'pkg/data', case + '.json'), td + '/p.json', '--config', cfg,
                        '-o', td + '/r.json', '--trace-output', td + '/t.json', '--log-output', td + '/l.txt'],
                       check=True, capture_output=True)
        return json.load(open(td + '/r.json'))


def slim_timeline(r):
    return [{'core': c['core_id'],
             'ops': [(o['pipe'], o['start'], o['end'], o['op']) for o in c['ops']]} for c in r['per_core_timeline']]


def timeline_ab(case='case_010', k=4):
    cand = load_candidates()
    c = min(cand[(2, case, k)], key=lambda x: x['makespan'])
    g = json.load(open(os.path.join(ROOT, 'pkg/data', case + '.json')))
    plan = build(g, k, c)
    out = {'case': case, 'k': k, 'source': c}
    for p, tag in ((1, 'A'), (2, 'B')):
        r = run(case, plan, p)
        out[tag] = {'makespan': r['makespan'], 'data_movement_bytes': r['data_movement_bytes'],
                    'timeline': slim_timeline(r)}
    json.dump(out, open(os.path.join(OUT, 'timeline_AB.json'), 'w'))
    print('timeline_AB', case, {t: out[t]['makespan'] for t in 'AB'})


def lockstep(case='case_044', k=4):
    cand = load_candidates()
    c = min(cand[(3, case, k)], key=lambda x: x['makespan'])
    g = json.load(open(os.path.join(ROOT, 'pkg/data', case + '.json')))
    plan = build(g, k, c)
    out = {'case': case, 'k': k, 'source': c}
    for bw, cfg in ((250, CFG), (60, os.path.join(ROOT, 'runs/sens/cfg/bw_60.txt'))):
        r = run(case, plan, 3, cfg)
        hit = {(e['core_id'], e['op_id']): e['event'] for e in r['cache_events'] if e['event'] in ('hit', 'miss')}
        key = {(e['core_id'], e['op_id']): e['tensor_id'] for e in r['cache_events'] if e['event'] in ('hit', 'miss')}
        reads = []
        for core in r['per_core_timeline']:
            for o in core['ops']:
                kk = (core['core_id'], o['op_id'])
                if o['op'] == 'COPY_IN' and kk in hit:
                    reads.append((core['core_id'], o['start'], o['end'], hit[kk], key[kk]))
        out[str(bw)] = {'makespan': r['makespan'], 'hit_rate': r['cache_stats']['hit_rate'], 'reads': reads}
    json.dump(out, open(os.path.join(OUT, 'lockstep.json'), 'w'))
    print('lockstep', case, {b: (out[b]['makespan'], round(out[b]['hit_rate'], 3)) for b in ('250', '60')})


if __name__ == '__main__':
    timeline_ab()
    lockstep()
