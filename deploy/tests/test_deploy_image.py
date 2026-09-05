import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'deploy-image.sh'


class DeploymentTests(unittest.TestCase):
    def run_deployment(self, failure='', command=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env').write_text('BACKEND_IMAGE=previous\nKEEP_SETTING=yes\n')
            (root / 'compose.yaml').write_text('services: {}\n')
            script = SCRIPT.read_text().replace('/opt/soccer-analysis-agent', str(root)).replace('/var/lock/soccer-backend-deploy.lock', str(root / 'lock'))
            (root / 'deploy.sh').write_text(script)
            mocks = {
                'flock': '#!/bin/sh\nexit 0\n',
                'docker': '#!/bin/sh\necho "$*" >> "$TEST_ROOT/docker.log"\nif [ "$1" = pull ] && [ "$FAILURE" = pull ]; then exit 1; fi\nif [ "$1" = compose ] && [ "$FAILURE" = startup ] && ! [ -f "$TEST_ROOT/failed" ]; then touch "$TEST_ROOT/failed"; exit 1; fi\n',
                'curl': '#!/bin/sh\n[ "$FAILURE" != health ]\n',
            }
            for name, contents in mocks.items():
                p = root / name
                p.write_text(contents)
                p.chmod(0o755)
            digest = 'sha256:' + 'a' * 64
            result = subprocess.run(['bash', str(root / 'deploy.sh')], capture_output=True, text=True, env={**os.environ, 'PATH': str(root) + ':' + os.environ['PATH'], 'TEST_ROOT': str(root), 'FAILURE': failure, 'SSH_ORIGINAL_COMMAND': command if command is not None else 'deploy ' + digest})
            log = root / 'docker.log'
            return result.returncode, (root / '.env').read_text(), log.read_text() if log.exists() else ''

    def test_success_preserves_other_settings(self):
        code, env, log = self.run_deployment()
        self.assertEqual(code, 0)
        self.assertIn('@sha256:' + 'a' * 64, env)
        self.assertIn('KEEP_SETTING=yes', env)
        self.assertEqual(log.count('compose up'), 1)

    def test_pull_failure_keeps_running_release(self):
        code, env, log = self.run_deployment('pull')
        self.assertNotEqual(code, 0)
        self.assertIn('BACKEND_IMAGE=previous', env)
        self.assertNotIn('compose up', log)

    def test_startup_and_health_failures_restore_previous_release(self):
        for failure in ('startup', 'health'):
            with self.subTest(failure=failure):
                code, env, log = self.run_deployment(failure)
                self.assertNotEqual(code, 0)
                self.assertIn('BACKEND_IMAGE=previous', env)
                self.assertEqual(log.count('compose up'), 2)

    def test_rejects_arbitrary_commands(self):
        for command in ('id', 'deploy latest', 'deploy sha256:' + 'a' * 64 + '; id'):
            with self.subTest(command=command):
                code, env, log = self.run_deployment(command=command)
                self.assertEqual(code, 2)
                self.assertEqual(log, '')


if __name__ == '__main__':
    unittest.main()
