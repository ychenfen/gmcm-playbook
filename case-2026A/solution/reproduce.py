# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具名称：Claude Code；版本/型号：Claude Opus 5.5；开发机构：Anthropic；版本颁布日期：2026 年 9 月 22 日
"""复现论文附录：把 plans/ 中的最终方案逐个交给官方评估程序，与 expected.csv 比对。

用法：
    python reproduce.py --pkg <官方材料包根目录> [--problems 1 2 3] [--cases case_001 ...] [--cores 2 3 4 5] [-j 4]

plans/p{P}_k{K}_{case}.json 是问题 P、K 核的最终方案，expected.csv 是附录中的 Makespan、额外搬运量和命中率。
"""
import argparse, csv, json, os, sys, subprocess, tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))


def run(args):
    pkg, p, k, case = args
    plan = os.path.join(HERE, 'plans', f'p{p}_k{k}_{case}.json')
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run([sys.executable, os.path.join(pkg, 'code', f'multicore_cut_evaluate_problem_{p}.py'),
                            os.path.join(pkg, 'data', case + '.json'), plan, '--config', os.path.join(pkg, 'data', 'config.txt'),
                            '-o', os.path.join(td, 'r.json'), '--trace-output', os.path.join(td, 't.json'),
                            '--log-output', os.path.join(td, 'l.txt')], capture_output=True, text=True)
        if r.returncode:
            return (p, k, case), None
        res = json.load(open(os.path.join(td, 'r.json')))
    return (p, k, case), {'makespan': res['makespan'],
                          'added_bytes': res['data_movement_bytes']['added_copy_bytes'],
                          'hit_rate': round((res.get('cache_stats') or {}).get('hit_rate') or 0.0, 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pkg', default='.', help='官方材料包根目录，默认当前目录')
    ap.add_argument('--problems', nargs='+', type=int, default=[1, 2, 3])
    ap.add_argument('--cases', nargs='+')
    ap.add_argument('--cores', nargs='+', type=int)
    ap.add_argument('-j', type=int, default=4)
    a = ap.parse_args()
    exp = {}
    for r in csv.DictReader(open(os.path.join(HERE, 'expected.csv'), encoding='utf-8')):
        exp[(int(r['problem']), int(r['k']), r['case'])] = r
    keys = [x for x in sorted(exp) if x[0] in a.problems and (not a.cases or x[2] in a.cases)
            and (not a.cores or x[1] in a.cores)]
    ok = bad = 0
    with ProcessPoolExecutor(max_workers=a.j) as ex:
        futs = [ex.submit(run, (a.pkg,) + key) for key in keys]
        for f in as_completed(futs):
            key, got = f.result()
            e = exp[key]
            match = got is not None and got['makespan'] == int(e['makespan']) and got['added_bytes'] == int(e['added_bytes'])
            if key[0] == 3 and got is not None:
                match = match and abs(got['hit_rate'] - float(e['hit_rate'])) < 1e-3
            ok += match; bad += not match
            print(f"问题{key[0]} {key[1]}核 {key[2]}: {'一致' if match else '不一致'}  "
                  f"评估 {got['makespan'] if got else '失败'} / 附录 {e['makespan']}", flush=True)
    print(f'==== 一致 {ok} / {ok + bad} ====')
    sys.exit(0 if bad == 0 else 1)


if __name__ == '__main__':
    main()
