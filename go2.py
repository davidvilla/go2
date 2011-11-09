#!/usr/bin/python
# -*- coding:utf-8; tab-width:4; mode:python -*-

# go2.py
#
# Copyright © 2004-2011 David Villa Alises
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA


import sys
import os

try:
    sys.path.remove(os.getcwd())
except (OSError, ValueError):
    pass

os.environ['LANG'] = 'C'

import pwd
import Queue
import tty
import select
import termios
import time
import signal
import re
from threading import Thread
import multiprocessing as mp
import multiprocessing.queues as mp_queues
import subprocess as subp
import shlex


from fs.osfs import OSFS
from fs import ResourceNotFoundError

import logging

import argparse


ESC = 27
CTRL_C = 3
ENTER = 13
HIGH = chr(27) + '[1m'
LOW  = chr(27) + '[m'


USERDIR    = os.environ['HOME']
GO2DIR     = os.path.join(USERDIR, '.go2')
#GO2INCLUDE = os.path.join(GO2DIR, 'include')
#GO2EXCLUDE = os.path.join(GO2DIR, 'exclude')
GO2HISTORY = os.path.join(GO2DIR, 'history')
GO2CACHE   = os.path.join(GO2DIR, 'cache')
#GO2CONFIG  = os.path.join(GO2DIR, 'config')
GO2TMP     = os.path.join(GO2DIR, 'tmp')
GO2LOG     = os.path.join(GO2DIR, 'log')

VERSION = '1.20111104'

ACTIVATION_CMD = "[ -e /usr/lib/go2/go2.sh ] && source /usr/lib/go2/go2.sh"
CD_MODE_CMD = "alias cd='go2 --cd'"

STOP = 'STOP'

logging.basicConfig(
    filename=os.path.join('/tmp/go2-%s' % pwd.getpwuid(os.getuid())[0]),
    filemode='w',
    format='%(asctime)-15s %(message)s',
    level=logging.DEBUG)


def go2setup(mode='r+'):
    try:
        if ACTIVATION_CMD in config.fs.getcontents(os.path.join(USERDIR, '.bashrc')):
            print('go2 already configured, skipping.')
            return 1

    except ResourceNotFoundError:
        pass

    with config.fs.open(os.path.join(USERDIR, '.bashrc'), 'w') as fd:
        fd.write("{0}\n{1}\n".format(ACTIVATION_CMD, CD_MODE_CMD))
        print('Setting up go2. It will be ready in next shell session.')


def rprint(cad=''):
    sys.stdout.write('\r%s' % cad)
    sys.stdout.flush()


def high(text):
    return config.before + text + config.after


class ListUniq(list):
    def append(self, item):
        if item in self:
            return

        list.append(self, item)

    def extend(self, other):
        for item in other:
            self.append(item)


def high_pattern(pattern, path):
    retval = ''
    begin = 0

    re_str = pattern2re_contain(pattern)
    mo = re.match(re_str, path, re.IGNORECASE)

    for i in range(1, mo.lastindex + 1):
        retval += mo.string[begin:mo.start(i)]
        retval += config.before + mo.group(i) + config.after
        begin = mo.end(i)

    retval += mo.string[begin:]
    return retval


class MatchLevel:
    NO_MATCH = -1
    START = 0
    START_IGNORECASE = 1
    CONTAIN = 2
    CONTAIN_IGNORECASE = 3


def pattern2re_start(pattern):
    return str.join('', ['.*/({0})[^/]*'.format(x) for x in pattern]) + '$'


def pattern2re_contain(pattern):
    return str.join('', ['.*/.*({0})[^/]*'.format(x) for x in pattern]) + '$'


def match(path):
#    if False and len(config.pattern) == 1:
#        pattern = config.pattern[0]
#        basename = os.path.basename(path)
#        if re.match(pattern, basename):
#            return MatchLevel.START
#
#        if re.match(pattern, basename, re.IGNORECASE):
#            return MatchLevel.START_IGNORECASE
#
#        if re.search(pattern, basename):
#            return MatchLevel.CONTAIN
#
#        if re.search(pattern, basename, re.IGNORECASE):
#            return MatchLevel.CONTAIN_IGNORECASE
#
#        return MatchLevel.NO_MATCH

    re_str = pattern2re_start(config.pattern)
    if re.match(re_str, path):
        return MatchLevel.START

    if re.match(re_str, path, re.IGNORECASE):
        return MatchLevel.START_IGNORECASE

    re_str = pattern2re_contain(config.pattern)
    if re.match(re_str, path):
        return MatchLevel.CONTAIN

    if re.match(re_str, path, re.IGNORECASE):
        return MatchLevel.CONTAIN_IGNORECASE

    return MatchLevel.NO_MATCH


def save_target(path):
    config.fs.setcontents(GO2TMP, path)


class PathStore:
    "Manage a file holding a path set"

    def __init__(self, path, size=1000):
        self.path = path
        self.size = size
        self.load()
#        self.log = logging.getLogger('PathStore [%s]' % os.path.split(path)[-1])

    def load(self):
        self.data = {}

        if not config.fs.exists(self.path):
            return

        try:
            with config.fs.open(self.path) as fd:
                for line in fd:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        visits, path = line.split(':', 1)
                    except ValueError:
                        visits, path = 1, line

                    self.data[path.strip()] = int(visits)
        finally:
            del fd

    def __iter__(self):
        def _cmp(p1, p2):
            retval = -cmp(p1[1], p2[1])
            if retval == 0:
                return cmp(p1[0], p2[0])

            return retval

        for path, visits in sorted(self.data.items(), cmp=_cmp):
            yield path

    def insert(self, seq):
#        self.log.debug("   Saving to file: %s (%s)" % (item,
#                                                      str(len(self.data))))
        if isinstance(seq, str):
            seq = [seq]

        for path in seq:
            visits = self.data.get(path, 0)
            self.data[path] = visits + 1

    def save(self):
        with config.fs.open(self.path, 'w') as fd:
            for path, visits in self.data.items()[:self.size]:
                fd.write("{0}:{1}\n".format(visits, path))

    def insert_and_save(self, item):
        self.insert(item)
        self.save()

    def __unicode__(self):
        return "<PathStore {0}>".format(self.path)


def save_in_history(path):
    PathStore(GO2HISTORY).insert_and_save(path)


def file_task(output, path_store):
    for path in path_store:
        level = match(path)
        if level == MatchLevel.NO_MATCH:
            continue

        if not config.fs.exists(path):
            del path_store.data[path]
            continue

        output.put((path, level))


class CommandTask:
    def __init__(self, output, command):
        self.output = output
        self.command = command

        self.ps = subp.Popen(
            shlex.split(command),
            bufsize    = 0,
            shell      = False,
            close_fds  = True,
            stdout     = subp.PIPE,
            stderr     = subp.PIPE,
            preexec_fn = os.setsid)

        logging.info('%s: starts', self)

        self.abort = False
        signal.signal(signal.SIGTERM, self.terminate)

        try:
            self.communicate()
        except IOError:
            self.terminate()

#    def is_alive2(self):
#        try:
#            self.ps.send_signal(0)
#        except OSError:
#            return False
#
#        return True

    def is_alive(self):
#        return self.ps.poll() is None
        value = os.waitpid(self.ps.pid, os.WNOHANG)
        logging.debug('%s: waitpid %s ', self, value)
        return value == (0, 0)
#        return os.waitpid(self.ps.pid, os.WNOHANG) == (0, 0)

    def terminate(self, *args):
        if self.abort:
            return

        self.abort = True
        logging.info('%s: terminate', self)

        try:
            self.ps.send_signal(signal.SIGTERM)
#            os.killpg(self.ps.pid, signal.SIGTERM)
            time.sleep(0.15)

            while self.is_alive():
                logging.info('%s: SIGKILLed', self)
                self.ps.send_signal(signal.SIGKILL)
#                os.killpg(self.ps.pid, signal.SIGKILL)
                time.sleep(0.1)

        except OSError, e:
            logging.error('%s: %s', self, e)

        # WARN: This kills the worker running this task
        sys.exit()

    def communicate(self):
        for path in self.ps.stdout:
            if self.abort:
                return

            path = path.strip()

            level = match(path)
            if level == MatchLevel.NO_MATCH:
                continue

            if not config.fs.exists(path):
                continue

            self.output.put((path, level))

    def __str__(self):
        return "CommandTask pid:{0} cmd:'{1}'".format(self.ps.pid, self.command)


def tree_task(output, root):
    CommandTask(output, "tree -dfin --noreport %s" % root)


class CancelException(Exception):
    pass


class NotMatchException(Exception):
    pass


class NotExistsException(Exception):
    pass


class TTY:
    def __init__(self):
        self.old_settings = tty.tcgetattr(sys.stdin)

    def set_raw(self):
        tty.setraw(sys.stdin)

    def restore(self):
        tty.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)


class UI:
    max_size = 26

    def __init__(self, pool):
        self.pool = pool
        self.paths = []
        self.alternate_paths = [list() for x in range(3)]
        self.menu_open = True

        self.poll = select.poll()
        self.poll.register(sys.stdin, select.POLLIN)

    def run(self):
        tty = TTY()
        tty.set_raw()

        try:
            election = self.wait_for_election()
        finally:
            tty.restore()
            rprint()

        return self.paths[election]

    def wait_for_election(self):
        while 1:
            self.process_pending()

            key = self.get_key()
            if key is None:
                if self.menu_open:
                    continue

                return 0

        election = self.key2election(key)
        if self.is_valid_election(election):
            logging.debug('election is %s', election)
            return election

    def get_key(self):
        keypress = self.poll.poll(100)
        if not keypress:
            return None

        return ord(sys.stdin.read(1))

    def process_pending(self):
        try:
            while 1:
                msg = self.pool.output_queue.get(timeout=0.1)
                self.process_match(*msg)

        except Queue.Empty:
            pass

        rprint(' ' * 20)

        if self.menu_open:
            if self.pool.has_tasks():
                rprint('Searching... ')
                return

            self.add_secondary_matches()

        self.menu_open = False

        if not self.paths:
            raise NotMatchException

        rprint('Select a path: ')

    def add_secondary_matches(self):
        for path_list in self.alternate_paths:
            if not self.menu_open:
                return

            if not path_list:
                continue

            rprint('   ~~~        \n')

            for path in path_list:
                self.process_match(path, 0)

            del path_list[:]

    def key2election(self, key):
        if key in [ESC, CTRL_C]:
            raise CancelException

        if key == ENTER:
            return 0

        return key - ord('a')

    def is_valid_election(self, election):
        return election in [None] + range(0, len(self.paths))

    def process_match(self, path, level):
        logging.debug("path:%s level:%s" % (path, level))
        target = self.paths if level == 0 else self.alternate_paths[level - 1]

        if path in target:
            return

        target.append(path)

        if level == MatchLevel.START and self.menu_open:
            self.add_to_menu(path)

    def add_to_menu(self, path):
        suffix = ''
        if path == os.getcwd():
            suffix = ' (the current directory)'

        if len(self.paths) == 1:
            suffix += ' [ENTER]'

        self.show_path(path, suffix)

        if len(self.paths) == self.max_size:
            self.menu_open = False
            rprint('Warning: Too many matches!\r\n')
            rprint('Select a path: ')

    def show_path(self, path, suffix):
        path = high_pattern(config.pattern, path)
        path = re.sub('^{0}'.format(USERDIR), '~', path)

        rprint("{char:c}: {path}{suffix}\r\n".format(**dict(
                    char = len(self.paths) + ord('a') - 1,
                    path = path,
                    suffix = suffix)))


def sleep(queue, t):
    time.sleep(t)


class ThreadStarted(Thread):
    def __init__(self, *args, **kargs):
        Thread.__init__(self, *args, **kargs)
        self.start()


class Worker(mp.Process):
    def __init__(self, tasks, output):
        self.tasks = tasks
        self.output = output
        mp.Process.__init__(self)
        self.start()

    def run(self):
        for func, args in iter(self.tasks.get, STOP):
            func(self.output, *args)
            self.tasks.task_done()

        self.tasks.task_done()


class TaskQueue(mp_queues.JoinableQueue):
    def unfinished_tasks_count(self):
        return self._unfinished_tasks._semlock._get_value()


class ProcessPool(object):
    def __init__(self):
        self.task_queue = TaskQueue()
        self.output_queue = mp.Queue()

        self.workers = [Worker(self.task_queue, self.output_queue)
                        for x in range(mp.cpu_count())]

    def add_task(self, func, *args):
        self.task_queue.put((func, args))

    def sleep_free_workers(self, time):
        for i in range(len(self.workers) - self.task_queue.unfinished_tasks_count()):
            self.add_task(sleep, time)

    def has_tasks(self):
        return self.task_queue.unfinished_tasks_count() != 0

    def terminate(self):
        logging.debug('pool: terminating')

        for w in self.workers:
            self.task_queue.put(STOP)

        time.sleep(0.1)

        term_threads = [ThreadStarted(target=w.terminate) for w in self.workers
                        if w.is_alive()]

        for t in term_threads:
            t.join()

        logging.debug('pool: terminated')


class Go2:
    def __init__(self):
        self.pool = ProcessPool()

    def main(self):
        retval = 0
        self.history = PathStore(GO2HISTORY)
        self.cache = PathStore(GO2CACHE)

        self.create_tasks()
        ui = UI(self.pool)

        try:
            target = ui.run()
            rprint("Changing to: {0}\n".format(high(target)))
            save_target(target)
            self.history.insert_and_save(target)
            logging.debug("saved history %s", len(ui.paths))
            self.cache.insert_and_save(ui.paths)

        except CancelException:
            print("Canceled by user")
            retval = 1

        except NotMatchException:
            print("Pattern does not match\r")
            retval = 1

        self.pool.terminate()
        logging.debug('end')
        return retval

    def not_overlapped_history(self):
        history_paths = []
        for p in sorted(self.history.data.keys(), key=len):
            if any(p.startswith(x) for x in history_paths):
                continue

            history_paths.append(p)

#        print str.join('\n', history_paths)
        return history_paths

    def create_tasks(self):
        self.pool.add_task(file_task, self.history)
#        self.pool.sleep_free_workers(1)

        self.pool.add_task(file_task, self.cache)

        paths = ListUniq()
        paths.extend([os.getcwd(), USERDIR])
#        paths.extend(self.not_overlapped_history())

        if config.from_root:
            paths.append('/')

        for path in paths:
            self.pool.add_task(tree_task, path)


def create_directory_wizzard(path):
    basetarget = os.path.basename(path)
    print "cd: '%s' does not exist. Cancel, Search or Make? (C,s,m):" % basetarget,

    try:
        answer = raw_input().lower()
    except KeyboardInterrupt:
        answer = ''
        print

    if len(answer) != 1 or answer not in 'sm':
        print 'Canceled'
        return 1

    if answer == 'm':
        try:
            config.fs.makedir(path)
        except OSError, e:
            print e
            sys.exit(1)

        print("go2: Making and changing to directory '%s'." % path)
        save_in_history(path)
        save_target(path)
        return 0

    # (s)earch
    Go2().main()


def chdir_decorator(wizzard=False):
    if not config.pattern:
        save_target(USERDIR)
        return 0

    params = str.join(' ', config.pattern)
    try:
        target = os.path.abspath(params)
    except IOError, e:
        logging.error(e)
        save_target(target)
        return 0

    if params == '-':
        save_target('-')
        return 0

    if config.fs.exists(target):
        save_in_history(target)
        save_target(target)
        return 0

    raise NotExistsException(target)


def get_config(args):
    parser = argparse.ArgumentParser(
        prog = 'go2',
        description = '''\
go2 is a fast directory finder.

This is version {0}, Copyright (C) 2004-2011 David Villa Alises.
go2 comes with ABSOLUTELY NO WARRANTY; This is free software, and you
are welcome to redistribute it under certain conditions; See COPYING
for details.'''.format(VERSION),
        epilog = '.',
        formatter_class = argparse.RawDescriptionHelpFormatter)

    parser.add_argument('pattern', nargs='*', help="pattern to find")
    parser.add_argument('--cd', dest='chdir', action="store_true",
                        help="change to given dir and add it to the cache (useful as 'cd' alias)")
    parser.add_argument('-i', '--ignore-case', dest='ignorecase',
                        action='store_true', default=False,
                        help="ignore case search")
    parser.add_argument('-r', '--from-root', dest='from_root',
                        action='store_true',
                        help="search in whole file system")
    parser.add_argument('--setup',
                        action='store_true',
                        help="install go2 in your .bashrc")
    parser.add_argument('--version', action='version', version='%(prog)s ' + VERSION)

    retval = parser.parse_args(args)
    retval.parser = parser

    # process args
    if retval.ignorecase:
        retval.pattern = [x.lower() for x in retval.pattern]

    retval.apply_case = str.lower if retval.ignorecase else str

    # application globals
    retval.fs = OSFS('/')
    retval.fs.makedir(GO2DIR, allow_recreate=True)

    retval.before = HIGH
    retval.after = LOW

    return retval


if __name__ == '__main__':
    config = get_config(sys.argv[1:])

    if config.setup:
        sys.exit(go2setup())

    if config.chdir:
        try:
            sys.exit(chdir_decorator())
        except NotExistsException, target:
            sys.exit(create_directory_wizzard(target.args[0]))

    if not config.pattern:
        print("go2.py: error: too few arguments\n")
        config.parser.print_help()
        sys.exit(1)

    sys.exit(Go2().main())
