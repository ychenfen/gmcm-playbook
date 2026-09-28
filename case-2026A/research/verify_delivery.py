# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
# 人工智能工具：OpenAI Codex（ChatGPT 桌面应用），版本/型号：【待团队按会话记录填写】，开发机构：OpenAI，版本发布日期：【待填写】
"""独立交付验收：固定 100 用例，核对任务/方案、CSV、曲线及可选的最新候选一致性。"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

import finalize as f


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(directory, require_current=False):
    directory = Path(directory).resolve()
    f.init_worker(str(directory))
    selected = f.read_json(directory / 'selected_tasks.json')
    cases = [f'case_{i:03d}' for i in range(1, 101)]
    expected_tags = {f'p{p}_k{k}_{c}' for c in cases for p, ks in
                     ((1, range(2, 6)), (2, range(1, 6)), (3, range(1, 6))) for k in ks}
    expected_tags |= {f'p2x_k{k}_{c}' for c in cases for k in range(1, 6)}
    require(len(selected) == 1900 and {f.task_tag(t) for t in selected} == expected_tags,
            'expected exactly 1400 main and 500 paired tasks')
    issues = f.validate_results(selected)
    require(not issues, f'evaluation/plan consistency failed: {issues[:10]}')
    status = f.read_json(directory / 'finalize_status.json')
    require(status.get('verified') is True and not status.get('worker_errors')
            and not status.get('validation_errors'), 'finalize status not verified')
    summary = f.read_json(directory / 'summary.json')
    require(summary['reproducibility']['evaluated'] == 1400, 'main count mismatch')
    require(summary['reproducibility']['paired_evaluated'] == 500, 'pair count mismatch')
    ev = {tag: f.read_json(directory / 'evals' / (tag + '.json')) for tag in expected_tags}
    sc = f.singlecore()
    for p in (1, 2):
        with (directory / f'appendix_p{p}.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        require(len(rows) == 100 and {r['case'] for r in rows} == set(cases), 'CSV cases mismatch')
        for row in rows:
            c = row['case']
            require(int(row['singlecore_makespan']) == sc[c], 'singlecore CSV mismatch')
            for k in range(2, 6):
                r = ev[f'p{p}_k{k}_{c}']
                require(int(row[f'makespan_k{k}']) == r['makespan'], 'makespan CSV mismatch')
                require(int(row[f'added_bytes_k{k}']) == r['data_movement_bytes']['added_copy_bytes'],
                        'traffic CSV mismatch')
                require(abs(float(row[f'speedup_k{k}']) - sc[c] / r['makespan']) <= 0.000051,
                        'speedup CSV mismatch')
        for k in range(2, 6):
            value = statistics.mean(sc[c] / ev[f'p{p}_k{k}_{c}']['makespan'] for c in cases)
            require(math.isclose(value, summary['speedup'][str(p)][str(k)], rel_tol=1e-12), 'curve mismatch')
    with (directory / 'appendix_p3.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 500 and {(r['case'], int(r['k'])) for r in rows}
            == {(c, k) for c in cases for k in range(1, 6)}, 'P3 CSV coverage mismatch')
    for row in rows:
        c, k = row['case'], int(row['k'])
        a, b, x = (ev[f'{p}_k{k}_{c}'] for p in ('p2', 'p3', 'p2x'))
        require(int(row['noL2_makespan']) == a['makespan'] and int(row['cache_makespan']) == b['makespan'],
                'P3 CSV makespan mismatch')
        for field, val in (('cache_speedup_best', a['makespan'] / b['makespan']),
                           ('cache_speedup_sameplan', x['makespan'] / b['makespan']),
                           ('cache_hit_rate', b['cache']['hit_rate'])):
            require(abs(float(row[field]) - val) <= 0.000051, f'P3 CSV {field} mismatch')
    for k in range(1, 6):
        expected = {
            'cache_speedup_best': statistics.mean(ev[f'p2_k{k}_{c}']['makespan'] / ev[f'p3_k{k}_{c}']['makespan'] for c in cases),
            'cache_speedup_sameplan': statistics.mean(ev[f'p2x_k{k}_{c}']['makespan'] / ev[f'p3_k{k}_{c}']['makespan'] for c in cases),
            'hit_rate_mean': statistics.mean(ev[f'p3_k{k}_{c}']['cache']['hit_rate'] for c in cases),
            'noL2_vs_single': statistics.mean(sc[c] / ev[f'p2_k{k}_{c}']['makespan'] for c in cases),
            'cache_vs_single': statistics.mean(sc[c] / ev[f'p3_k{k}_{c}']['makespan'] for c in cases),
        }
        require(summary['p3'][str(k)]['n'] == 100, 'P3 summary coverage mismatch')
        for field, value in expected.items():
            require(math.isclose(value, summary['p3'][str(k)][field], rel_tol=1e-12), f'P3 summary {field} mismatch')
    current = {f.task_tag(t): t[-1] for t in f.tasks(f.load_candidates(), cases)}
    pending = [f.task_tag(t) for t in selected if current[f.task_tag(t)] != t[-1]]
    if require_current:
        require(not pending, f'new candidates require refresh: {pending[:20]}')
    files = [directory / 'summary.json', directory / 'selected_tasks.json']
    files += list(directory.glob('appendix_p*.csv'))
    report = {'verified': True, 'main': 1400, 'pairs': 500, 'csv_rows': [100, 100, 500],
              'current_candidates_required': require_current, 'pending_current_tasks': pending,
              'artifact_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    f.atomic_json(str(directory / 'verification.json'), report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dir', default=f.OUT)
    parser.add_argument('--require-current', action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify(args.dir, args.require_current), ensure_ascii=False, indent=2))
