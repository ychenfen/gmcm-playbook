# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方公布为准）
"""鲁棒性分析：硬件参数扰动 ±20% 时，本文最终方案相对朴素方案的优势是否保持。

只作分析，官方结果仍用固定 config.txt。扰动配置写在 runs/robust/configs/，不修改官方配置文件。
样本：三族各取 10 例（按编号等间隔抽取），4 核，问题1、2。
每个（用例，问题，配置）评估两份方案：deliverables 中的最终方案、朴素方案（分量装箱 α=0.25）。
输出 runs/robust/{case}_p{P}_{cfg}_{final|naive}.json，断点续跑。
"""
import json, os, sys, subprocess, tempfile, argparse, time
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep2 import make_plan, pad

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
PY = sys.executable
OUTD = os.path.join(ROOT, 'runs', 'robust')
BASE = open(os.path.join(ROOT, 'pkg', 'data', 'config.txt'), encoding='utf-8').read()
VARIANTS = {                      # 名称 -> (键, 新值) 列表
    'bw48': [('bandwidth', 48)], 'bw72': [('bandwidth', 72)],
    'sync08': [('task_cross_core_wait_cycles', 800), ('task_same_core_wait_cycles', 80), ('cross_core_copy_delay_cycles', 400)],
    'sync12': [('task_cross_core_wait_cycles', 1200), ('task_same_core_wait_cycles', 120), ('cross_core_copy_delay_cycles', 600)],
}


def write_configs():
    os.makedirs(os.path.join(OUTD, 'configs'), exist_ok=True)
    paths = {}
    for name, kv in VARIANTS.items():
        lines = []
        for line in BASE.splitlines():
            parts = line.split()
            for k, v in kv:
                if parts and parts[0] == k:
                    line = f'{k} {v}'
            lines.append(line)
        p = os.path.join(OUTD, 'configs', f'{name}.txt')
        open(p, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
        paths[name] = p
    return paths


def sample_cases():
    conn = json.load(open(os.path.join(ROOT, 'runs', 'connectivity.json')))
    fam = lambda x: 'I' if x > 0.8 else ('II' if x >= 0.3 else 'III')
    out = []
    for F in ('I', 'II', 'III'):
        cs = sorted(r['case'] for r in conn if fam(r['top_comp_frac_cyc']) == F)
        step = max(1, len(cs) // 10)
        out += cs[::step][:10]
    return out


def job(a):
    case, p, cfg_name, cfg_path, which = a
    gp = os.path.join(ROOT, 'pkg', 'data', case + '.json')
    if which == 'final':
        plan = json.load(open(os.path.join(ROOT, 'deliverables', 'plans', f'p{p}_k4_{case}.json')))
    else:
        plan = pad(make_plan(json.load(open(gp)), 4, 'lpt', 0.25), 4)
    import hashlib
    h = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()[:12]
    out = os.path.join(OUTD, f'{case}_p{p}_{cfg_name}_{which}.json')
    if os.path.exists(out):
        try:
            old = json.load(open(out))
            # 朴素方案是确定性生成的，无哈希的旧记录可沿用；最终方案必须哈希一致，否则重评
            if old.get('plan_hash') == h or (which == 'naive' and 'plan_hash' not in old):
                return 'skip'
        except Exception:
            pass
    with tempfile.TemporaryDirectory() as td:
        pp = os.path.join(td, 'p.json'); json.dump(plan, open(pp, 'w'))
        r = subprocess.run([PY, os.path.join(ROOT, 'pkg', 'code', f'multicore_cut_evaluate_problem_{p}.py'), gp, pp,
                            '--config', cfg_path, '-o', td + '/r.json', '--trace-output', td + '/t.json',
                            '--log-output', td + '/l.txt'], capture_output=True, text=True, timeout=7200)
        rec = {'case': case, 'problem': p, 'config': cfg_name, 'plan': which, 'plan_hash': h}
        if r.returncode:
            rec['err'] = (r.stderr or r.stdout)[-300:]
        else:
            rec['makespan'] = json.load(open(td + '/r.json'))['makespan']
    json.dump(rec, open(out + '.tmp', 'w')); os.replace(out + '.tmp', out)
    return 'done'


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('-j', type=int, default=4); a = ap.parse_args()
    cfg = write_configs()
    cfg['official'] = os.path.join(ROOT, 'pkg', 'data', 'config.txt')
    cases = sample_cases()
    size = {c: os.path.getsize(os.path.join(ROOT, 'pkg', 'data', c + '.json')) for c in cases}
    js = [(c, p, n, path, w) for c in sorted(cases, key=lambda c: size[c]) for p in (1, 2)
          for n, path in cfg.items() for w in ('final', 'naive')]
    print(f'鲁棒性作业 {len(js)} 个，用例 {len(cases)}', flush=True)
    fail = 0
    with ProcessPoolExecutor(max_workers=a.j) as ex:
        for i, f in enumerate(as_completed([ex.submit(job, j) for j in js]), 1):
            try:
                f.result()
            except Exception as e:
                fail += 1; print('异常', e, flush=True)
            if i % 50 == 0:
                print(f'  进度 {i}/{len(js)} {time.strftime("%H:%M:%S")}', flush=True)
    print(f'==== 鲁棒性结束：作业 {len(js)}，异常 {fail} ====', flush=True)
