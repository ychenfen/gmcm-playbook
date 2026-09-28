# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
# 人工智能工具：OpenAI Codex（ChatGPT 桌面应用），版本/型号：【待团队按会话记录填写】，开发机构：OpenAI，版本发布日期：【待填写】
"""隔离回归：不调用正式评估器，不写正式 deliverables，也不终止真实进程。"""
import concurrent.futures
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch

import finalize as f
import stop_compute as stop


class FinalizeSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for d in ('evals', 'plans', 'pkg/data'):
            (self.root / d).mkdir(parents=True)
        (self.root / 'pkg/data/case_001.json').write_text('{}')
        self.plan = {'node_to_subgraph': {'1': 0}, 'core_schedules': [[0]]}
        self.source = {'src': 'coarsen', 'makespan': 7}
        self.task = ('main', 3, 'case_001', 1, self.source)
        self.patches = [patch.object(f, 'ROOT', str(self.root)), patch.object(f, 'OUT', str(self.root)),
                        patch.object(f, 'build', return_value=self.plan)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def seed(self, **changes):
        r = {'kind': 'main', 'problem': 3, 'case': 'case_001', 'k': 1, 'source': self.source,
             'makespan': 7, 'reproduced': True, 'plan_sha256': f.plan_hash(self.plan)}
        r.update(changes)
        f.atomic_json(str(self.root / 'evals/p3_k1_case_001.json'), r)
        f.atomic_json(str(self.root / 'plans/p3_k1_case_001.json'), self.plan)

    def test_real_future_exception_is_reported(self):
        with patch.object(f, 'job', side_effect=RuntimeError('injected worker failure')):
            failed, counts = f.run_tasks([self.task], 1, concurrent.futures.ThreadPoolExecutor)
        self.assertEqual(len(failed), 1)
        self.assertIn('injected worker failure', failed[0]['error'])
        self.assertFalse(counts)

    def test_missing_and_stale_outputs_rejected(self):
        self.assertTrue(f.validate_results([self.task]))
        self.seed(source={'src': 'sweep', 'makespan': 8})
        self.assertTrue(f.validate_results([self.task]))
        with self.assertRaisesRegex(ValueError, 'refusing stale'):
            f.summarize(['case_001'], [self.task])
        self.assertFalse((self.root / 'summary.json').exists())

    def test_failed_eval_preserves_previous_files(self):
        self.seed(source={'src': 'sweep', 'makespan': 8})
        old = (self.root / 'evals/p3_k1_case_001.json').read_bytes()
        with patch.object(f, 'evaluate', return_value={'err': 'test failure'}):
            with self.assertRaisesRegex(RuntimeError, 'official evaluation failed'):
                f.job(self.task)
        self.assertEqual(old, (self.root / 'evals/p3_k1_case_001.json').read_bytes())

    def test_valid_reuse_and_tampered_plan(self):
        self.seed()
        with patch.object(f, 'evaluate') as ev:
            self.assertEqual(f.job(self.task)[1], 'skip')
            ev.assert_not_called()
        self.assertFalse(f.validate_results([self.task]))
        (self.root / 'plans/p3_k1_case_001.json').write_text('{}')
        self.assertTrue(f.validate_results([self.task]))

    def test_mismatch_not_published(self):
        with patch.object(f, 'evaluate', return_value={'makespan': 9}):
            with self.assertRaisesRegex(RuntimeError, 'makespan mismatch'):
                f.job(self.task)
        self.assertFalse((self.root / 'evals/p3_k1_case_001.json').exists())

    def test_missing_candidate_group_is_error(self):
        with self.assertRaisesRegex(ValueError, 'missing candidate'):
            f.tasks({}, ['case_001'])

    def test_all_source_labels(self):
        self.assertEqual([f.src_label(c) for c in ({'src': 'sweep', 'algo': 'lpt'},
                         {'src': 'localsearch'}, {'src': 'coarsen'}, {'src': 'crosseval'})],
                         ['lpt', 'localsearch', 'coarsen', 'crosseval'])


class StopScope(unittest.TestCase):
    def test_exact_project_scope_and_descendants(self):
        root = Path('/home/ubuntu/A_work')
        def p(pid, ppid, argv, cwd=str(root)):
            return {'pid': pid, 'ppid': ppid, 'argv': argv, 'cwd': cwd, 'start': pid}
        ps = {
            1: p(1, 0, ['tmux', 'new-session', 'bash -c python3 src/crosseval.py']),
            2: p(2, 1, ['python3', 'src/crosseval.py']),
            3: p(3, 2, ['python3', '/home/ubuntu/A_work/pkg/code/multicore_cut_evaluate_problem_3.py']),
            4: p(4, 3, ['/bin/sleep', '2']),
            5: p(5, 1, ['python3', 'src/crosseval.py'], '/home/ubuntu/other'),
            6: p(6, 1, ['ssh', 'host', 'cd /home/ubuntu/A_work && python3 src/crosseval.py']),
            7: p(7, 1, ['python3', 'src/stop_compute.py']),
        }
        self.assertEqual(set(stop.targets(ps, root, 7)), {2, 3, 4})

    def test_pid_reuse_not_signalled(self):
        with patch.object(stop, 'read_process', return_value={'pid': 2, 'start': 99}), \
                patch.object(stop.os, 'kill') as kill:
            self.assertFalse(stop.safe_signal({'pid': 2, 'start': 1}, 15))
            kill.assert_not_called()

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux /proc integration only')
    def test_linux_stops_only_fixture_job_and_child(self):
        with tempfile.TemporaryDirectory(prefix='stop-safety-') as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / 'runs').mkdir()
            script = root / 'src/crosseval.py'
            script.write_text('import subprocess,time\n'
                              'p=subprocess.Popen(["/bin/sleep","120"])\n'
                              'print(p.pid,flush=True)\n'
                              'time.sleep(120)\n')
            unrelated = subprocess.Popen(['/bin/sleep', '120'])
            worker = subprocess.Popen([sys.executable, str(script)], cwd=root,
                                      stdout=subprocess.PIPE, text=True)
            child = None
            try:
                child = int(worker.stdout.readline())
                self.assertEqual(stop.stop(root, grace=1), 0)
                worker.wait(timeout=3)
                self.assertIsNone(stop.read_process(child))
                self.assertIsNone(unrelated.poll())
                self.assertEqual(json.loads((root / 'runs/STOPPED_CODEX.json').read_text())['state'], 'stopped')
            finally:
                worker.stdout.close()
                for process in (worker, unrelated):
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=3)
                if child is not None and stop.read_process(child) is not None:
                    stop.safe_signal(stop.read_process(child), 15)


if __name__ == '__main__':
    unittest.main()
