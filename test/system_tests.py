# True black-box system tests: go2.py is run as a real subprocess and
# observed from the outside, using prego (ported from the old atheist-format
# test/system/*.test files).

import os
import signal

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
