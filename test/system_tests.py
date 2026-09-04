# True black-box system tests: go2.py is run as a real subprocess and
# observed from the outside, using prego (ported from the old atheist-format
# test/system/*.test files).

import os
import pty
import signal
import subprocess
import tempfile
import unittest

import hamcrest
from prego import TestCase, Task

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GO2PY = os.path.join(REPO_ROOT, 'go2.py')


class NoArguments(TestCase):
    def test_shows_usage_and_exits_1(self):
        task = Task(desc='go2 without arguments')
        cmd = task.command('{0} --skip-config'.format(GO2PY), expected=1)

        task.assert_that(
            cmd.stdout.content, hamcrest.contains_string('too few arguments'))
        task.assert_that(
            cmd.stdout.content,
            hamcrest.contains_string('go2 is a fast directory finder'))


class TreeKilled(TestCase):
    def test_tree_subprocess_dies_when_go2_is_killed(self):
        "go2's own SIGTERM handler must cascade the kill down to its tree child"
        search = Task(desc='go2 background search', detach=True)
        search.command(
            '{0} --skip-config -p /usr sha'.format(GO2PY),
            timeout=2, expected=-signal.SIGTERM)

        check = Task(desc='tree must not survive its parent')
        check.command('! pgrep -x tree')


class SearchWithoutConfigFile(unittest.TestCase):
    """Reported crash: 'NameError: name config is not defined' raised inside
    a search worker when go2 runs with no ~/.go2/config file.

    'config' is a module global assigned only inside go2.py's
    `if __name__ == '__main__':` guard; worker subprocesses need to inherit
    it via fork. Uses a real pty (rather than prego's plain Popen) because
    go2 requires a tty for stdin even before spawning workers.
    """

    def test_runs_clean_with_no_config_file_present(self):
        with tempfile.TemporaryDirectory() as home, \
                tempfile.TemporaryDirectory() as search_root:
            target = os.path.join(search_root, 'book')
            os.mkdir(target)

            master_fd, slave_fd = pty.openpty()
            env = dict(os.environ, HOME=home)

            proc = subprocess.Popen(
                [GO2PY, '-l', '-p', search_root, 'book'],
                stdin=slave_fd, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, env=env, text=True,
                start_new_session=True)
            os.close(slave_fd)
            try:
                try:
                    out, _ = proc.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    # a crashed worker leaves the (non-daemon) pool hanging
                    # forever instead of exiting; kill go2's whole process
                    # group (a lone proc.kill() leaves orphaned workers
                    # holding the stdout pipe open, so communicate() would
                    # never see EOF) and surface whatever was printed before
                    # we gave up, since that's the actual failure signal
                    # (e.g. the NameError traceback)
                    os.killpg(proc.pid, signal.SIGKILL)
                    out, _ = proc.communicate()
                    self.fail(
                        "go2 did not exit within 10s (a worker likely "
                        "crashed and hung the pool); captured output:\n"
                        + out)
            finally:
                os.close(master_fd)

            self.assertFalse(
                os.path.exists(os.path.join(home, '.go2', 'config')),
                "test setup error: a config file was unexpectedly present")

            hamcrest.assert_that(out, hamcrest.is_not(
                hamcrest.contains_string('NameError')))
            hamcrest.assert_that(out, hamcrest.is_not(
                hamcrest.contains_string('Traceback')))
            hamcrest.assert_that(out, hamcrest.contains_string(target))
            self.assertEqual(0, proc.returncode)
