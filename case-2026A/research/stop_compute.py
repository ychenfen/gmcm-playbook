# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
# 人工智能工具：OpenAI Codex（ChatGPT 桌面应用），版本/型号：【待团队按会话记录填写】，开发机构：OpenAI，版本发布日期：【待填写】
"""Linux 项目计算截止器：按确切脚本路径识别作业及子进程，验证退出后才写标记。"""
import argparse
import datetime
import json
import os
from pathlib import Path
import signal
import tempfile
import time

SCRIPTS = {
    'src/sweep.py', 'src/sweep2.py', 'src/ls_driver.py', 'src/ls_driver2.py',
    'src/coarsen.py', 'src/crosseval.py', 'src/finalize.py', 'src/sens_cache.py',
    'run_all.sh', 'run_stage2.sh', 'run_tail.sh', 'run_co.sh', 'run_k1.sh',
    'pkg/code/multicore_cut_evaluate_problem_1.py',
    'pkg/code/multicore_cut_evaluate_problem_2.py',
    'pkg/code/multicore_cut_evaluate_problem_3.py',
}


def read_process(pid, proc_root=Path('/proc')):
    try:
        path = proc_root / str(pid)
        # comm 可以包含空格和括号，取最后一个右括号之后的字段。
        stat = (path / 'stat').read_text().rsplit(')', 1)[1].split()
        if stat[0] == 'Z':
            return None
        argv = [s.decode(errors='replace') for s in (path / 'cmdline').read_bytes().split(b'\0') if s]
        return {'pid': int(pid), 'ppid': int(stat[1]), 'start': int(stat[19]),
                'argv': argv, 'cwd': os.readlink(path / 'cwd')}
    except (OSError, ValueError, IndexError):
        return None


def snapshot():
    return {p['pid']: p for entry in Path('/proc').iterdir() if entry.name.isdigit()
            if (p := read_process(entry.name)) is not None}


def is_job(process, root):
    allowed = {str(root / name) for name in SCRIPTS}
    for token in process['argv'][1:]:
        if not token or token.startswith('-'):
            continue
        # 对独立 argv 中的路径做精确匹配；不会匹配 SSH、tmux 或 bash -c 的整串命令。
        path = Path(token)
        candidate = os.path.normpath(str(path if path.is_absolute() else Path(process['cwd']) / path))
        if candidate in allowed:
            return True
    return False


def targets(processes, root, own_pid=None):
    selected = {pid for pid, p in processes.items() if pid != own_pid and is_job(p, root)}
    while True:
        children = {pid for pid, p in processes.items() if p['ppid'] in selected and pid != own_pid}
        if children <= selected:
            return {pid: processes[pid] for pid in selected}
        selected |= children


def safe_signal(process, sig):
    current = read_process(process['pid'])
    if current is None or current['start'] != process['start']:
        return False                 # 退出或 PID 已复用，不能误杀新进程。
    try:
        os.kill(process['pid'], sig)
        return True
    except ProcessLookupError:
        return False


def write_marker(root, result):
    dest = root / 'runs/STOPPED_CODEX.json'
    fd, tmp = tempfile.mkstemp(prefix='.stop-codex-', dir=dest.parent)
    try:
        with os.fdopen(fd, 'w') as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def stop(root, grace=8):
    started = time.monotonic()
    signalled = set()
    initial = targets(snapshot(), root, os.getpid())
    while True:
        live = targets(snapshot(), root, os.getpid())
        if not live:
            time.sleep(0.5)
            live = targets(snapshot(), root, os.getpid())
            if not live:
                break
        sig = signal.SIGTERM if time.monotonic() - started < grace else signal.SIGKILL
        for process in live.values():
            key = (process['pid'], process['start'], sig)
            if key not in signalled:
                safe_signal(process, sig)
                signalled.add(key)
        if time.monotonic() - started > grace + 10:
            break
        time.sleep(0.25)
    remaining = targets(snapshot(), root, os.getpid())
    result = {'time': datetime.datetime.now().astimezone().isoformat(), 'root': str(root),
              'state': 'stopped' if not remaining else 'failed',
              'initial_pids': sorted(initial), 'remaining_pids': sorted(remaining),
              'scope_scripts': sorted(SCRIPTS)}
    write_marker(root, result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 1 if remaining else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--dry-run', action='store_true')
    action.add_argument('--now', action='store_true')
    action.add_argument('--deadline', help='带时区的 ISO 时间；到时才停止本项目计算')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    if not Path('/proc/self').exists() or not (root / 'pkg/data/config.txt').is_file():
        parser.error('requires Linux /proc and this project config')
    if args.dry_run:
        selected = targets(snapshot(), root, os.getpid())
        print(json.dumps(list(selected.values()), ensure_ascii=False, indent=2))
        return 0
    if args.deadline:
        deadline = datetime.datetime.fromisoformat(args.deadline)
        if deadline.tzinfo is None:
            parser.error('deadline must include timezone')
        print(f'armed: {deadline.isoformat()} root={root}', flush=True)
        while time.time() < deadline.timestamp():
            time.sleep(max(0, min(20, deadline.timestamp() - time.time())))
    return stop(root)


if __name__ == '__main__':
    raise SystemExit(main())
