# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具名称：Claude Code；版本/型号：Claude Opus 5.5；开发机构：Anthropic；版本颁布日期：2026 年 9 月 22 日
"""多核切图与调度求解（问题 1/2/3 通用），输出格式见赛题附录 B.5。

用法：
    python solve.py data/<case>.json -n <核数> --problem <1|2|3> [--config data/config.txt] [-o 方案文件] [-j 并行数] [--fewer-cores]

在官方材料包根目录下运行时自动找到 code/；方案默认写到计算图同目录的 <case>_multicore_res.json，
与官方示例生成器一致，评估程序省略方案参数时即可直接读取。

先用三种构造算法各 3 组参数生成候选（alpha 取 0.25/1/4，W 取 16/256/4096，lambda 取 2000/10000/50000），
交给对应问题的官方评估程序选出 Makespan 最小的方案，再对它做成组合并（宽度 2~128，3 种范围）。
加 --fewer-cores 时同时生成 k'<k 核的方案并补空核。
论文最终结果另外用了更大的参数网格、局部搜索和交叉复评，代码在 research_code/ 中；
附录中的数字可用 reproduce.py 从最终方案文件直接复现。
"""
import argparse, json, os, sys, subprocess, tempfile, time
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIGS = [('lpt', 0.25), ('lpt', 1), ('lpt', 4), ('band', 16), ('band', 256), ('band', 4096),
           ('phase', 2000), ('phase', 10000), ('phase', 50000)]
WIDTHS = (2, 4, 8, 16, 32, 64, 128)
MODES = ('all', 'last', 'others')


def find_code_dir(pkg, graph):
    # 官方材料包的 code/ 目录：优先用 --pkg；否则依次尝试当前目录、计算图上一级目录
    tries = [pkg] if pkg else [os.getcwd(), os.path.dirname(os.path.dirname(os.path.abspath(graph)))]
    for root in tries:
        code = os.path.join(root, 'code')
        if os.path.exists(os.path.join(code, 'stub_multicore_cut_and_schedule.py')):
            sys.path.insert(0, code)
            sys.path.insert(0, HERE)
            return code
    sys.exit('找不到官方材料包的 code/ 目录，请在材料包根目录下运行，或用 --pkg 指定材料包根目录')


def build(g, k, algo, div):
    from nmcs.algos import build_plan_lpt
    from nmcs.algos2 import build_plan_band
    from nmcs.algos4 import build_plan_phase
    if algo == 'lpt':
        return build_plan_lpt(g, k, chunk_div=div)
    if algo == 'band':
        return build_plan_band(g, k, n_bands=int(div))
    return build_plan_phase(g, k, comm_weight=1.0, sync_penalty=div)


def pad(plan, k):
    # k' 核方案补空核成为 k 核方案（题目允许某些核的子图序列为空）
    cs = plan['core_schedules']
    return {'node_to_subgraph': plan['node_to_subgraph'], 'core_schedules': cs + [[] for _ in range(k - len(cs))]}


def merge_blocks(plan, width, mode):
    # 成组合并：每个操作的核心不变，把同核相邻的 width 个子图并为一个；mode 决定作用于哪些核
    last = len(plan['core_schedules']) - 1
    remap, sched = {}, []
    for core, order in enumerate(plan['core_schedules']):
        active = mode == 'all' or (mode == 'last' and core == last) or (mode == 'others' and core != last)
        stride = width if active else 1
        merged = []
        for i in range(0, len(order), stride):
            merged.append(order[i])
            for s in order[i:i + stride]:
                remap[s] = order[i]
        sched.append(merged)
    return {'node_to_subgraph': {op: remap[sg] for op, sg in plan['node_to_subgraph'].items()}, 'core_schedules': sched}


def evaluate(args):
    # 调用官方评估程序，成功返回 (makespan, 摘要)，失败返回 (None, 报错信息)
    code, graph_path, plan, problem, cfg = args
    with tempfile.TemporaryDirectory() as td:
        pp = os.path.join(td, 'plan.json')
        json.dump(plan, open(pp, 'w'))
        r = subprocess.run([sys.executable, os.path.join(code, f'multicore_cut_evaluate_problem_{problem}.py'),
                            graph_path, pp, '--config', cfg, '-o', os.path.join(td, 'r.json'),
                            '--trace-output', os.path.join(td, 't.json'), '--log-output', os.path.join(td, 'l.txt')],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return None, (r.stderr or r.stdout)[-300:]
        res = json.load(open(os.path.join(td, 'r.json')))
        return res['makespan'], {'makespan': res['makespan'], 'data_movement_bytes': res.get('data_movement_bytes'),
                                 'cache_hit_rate': (res.get('cache_stats') or {}).get('hit_rate')}


def main():
    ap = argparse.ArgumentParser(description='多核切图与调度求解')
    ap.add_argument('graph', help='计算图 JSON（附录 B.3 格式）')
    ap.add_argument('-n', '--num-cores', '--cores', dest='cores', type=int, required=True)
    ap.add_argument('--problem', type=int, choices=(1, 2, 3), required=True, help='按哪个问题的评估程序选优')
    ap.add_argument('--config', help='固定评估配置，默认取计算图所在目录的 config.txt')
    ap.add_argument('-o', '--output', help='方案文件路径，默认 <计算图去掉 .json>_multicore_res.json')
    ap.add_argument('--pkg', help='官方材料包根目录，默认在当前目录或计算图上一级目录中查找 code/')
    ap.add_argument('-j', type=int, default=4, help='并行评估进程数')
    ap.add_argument('--fewer-cores', action='store_true', help="同时尝试只用 k'<k 个核（核数补齐）")
    a = ap.parse_args()
    graph = os.path.abspath(a.graph)
    code = find_code_dir(a.pkg, graph)
    cfg = os.path.abspath(a.config) if a.config else os.path.join(os.path.dirname(graph), 'config.txt')
    if not os.path.exists(cfg):
        sys.exit(f'找不到配置文件 {cfg}，请用 --config 指定')
    g = json.load(open(graph, encoding='utf-8'))
    case = os.path.basename(graph)[:-5] if graph.endswith('.json') else os.path.basename(graph)
    out_plan = os.path.abspath(a.output) if a.output else graph[:-5] + '_multicore_res.json'
    k = a.cores
    t0 = time.time()
    ks = range(1, k + 1) if a.fewer_cores else [k]
    cands = [(f'{al}_{dv:g}_k{kk}', pad(build(g, kk, al, dv), k)) for kk in ks for al, dv in CONFIGS]
    with ProcessPoolExecutor(max_workers=a.j) as ex:
        res = list(ex.map(evaluate, [(code, graph, p, a.problem, cfg) for _, p in cands]))
    report = [{'name': n, 'makespan': m, 'info': info} for (n, _), (m, info) in zip(cands, res)]
    ok = [(m, i) for i, (m, _) in enumerate(res) if m is not None]
    if not ok:
        sys.exit('所有构造候选均评估失败：' + str(res[0][1]))
    best_m, bi = min(ok)
    best_name, best_plan = cands[bi]
    variants = [(f'{best_name}+w{w}_{md}', merge_blocks(best_plan, w, md)) for w in WIDTHS for md in MODES]
    with ProcessPoolExecutor(max_workers=a.j) as ex:
        vres = list(ex.map(evaluate, [(code, graph, p, a.problem, cfg) for _, p in variants]))
    for (n, p), (m, info) in zip(variants, vres):
        report.append({'name': n, 'makespan': m, 'info': info})
        if m is not None and m < best_m:
            best_m, best_name, best_plan = m, n, p
    os.makedirs(os.path.dirname(out_plan), exist_ok=True)
    with open(out_plan, 'w', encoding='utf-8') as f:
        json.dump(best_plan, f)              # 顶层只有 node_to_subgraph 与 core_schedules（附录 B.5）
    report_path = out_plan[:-len('_multicore_res.json')] + f'_p{a.problem}_k{k}_report.json' \
        if out_plan.endswith('_multicore_res.json') else out_plan + '.report.json'
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump({'case': case, 'cores': k, 'problem': a.problem, 'best': best_name, 'makespan': best_m,
                   'seconds': round(time.time() - t0, 1), 'candidates': report}, f, ensure_ascii=False, indent=1)
    print(f'{case} 问题{a.problem} {k} 核：最优 {best_name}，Makespan {best_m:,}，用时 {time.time() - t0:.1f} 秒')
    print(f'方案 → {out_plan}')


if __name__ == '__main__':
    main()
