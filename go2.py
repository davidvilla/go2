#!/usr/bin/python3
# -*- coding:utf-8; tab-width:4; mode:python -*-

# go2.py
#
# Copyright © 2004-2015 David Villa Alises
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

__version__ = '2.20181225.7'

DESCRIPTION = f'''\
go2 is a fast directory finder.

This is version {__version__ = '2.20181225.7'
go2 comes with ABSOLUTELY NO WARRANTY; This is free software, and you
are welcome to redistribute it under certain conditions; See COPYING
for details.'''

import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

try:
    sys.path.remove(os.getcwd())
except (OSError, ValueError):
    pass

import pwd
import tty
import termios
import time
import signal
import re
import logging
import locale
import atexit

from threading import Thread
import multiprocessing as mp
import multiprocessing.queues as mp_queues
import subprocess as subp
import shlex
from traceback import print_exc
from itertools import cycle
from fnmatch import fnmatch
from functools import cmp_to_key

from gi.repository import GObject, GLib
import argparse
from osfs import OSFS, ResourceNotFoundError

ESC = 27
CTRL_C = 3
ENTER = 13
HIGH = chr(27) + '[1m'
LOW  = chr(27) + '[m'


USERDIR = os.environ['HOME']

try:
    CWD = os.getcwd()
except OSError:
    CWD = USERDIR

GO2DIR     = os.path.join(USERDIR, '.go2')
GO2IGNORE  = os.path.join(GO2DIR, 'ignore')
GO2HISTORY = os.path.join(GO2DIR, 'history')
GO2CACHE   = os.path.join(GO2DIR, 'cache')
#GO2CONFIG  = os.path.join(GO2DIR, 'config')
GO2TMP     = os.path.join(GO2DIR, 'tmp')
GO2LOG     = os.path.join(GO2DIR, 'log')
GO2ERRORS  = os.path.join(GO2DIR, 'errors')

ACTIVATION_CMD = "[ -e /usr/lib/go2/go2.sh ] && source /usr/lib/go2/go2.sh"
CD_MODE_CMD = """
function go2-cd() {
  if type go2 &> /dev/null; then
    go2 --cd $*
  else
    \cd $*
  fi
}
alias cd='go2-cd'"""

STOP = 'STOP'


# os.path.join('/tmp/go2-%s' % pwd.getpwuid(os.getuid())[0]),

if not os.path.exists(GO2DIR):
    os.mkdir(GO2DIR)

logging.basicConfig(
    filename=GO2LOG,
    format='%(asctime)-15s %(message)s',
    level=logging.DEBUG)


class MyLogger:
    def __init__(self):
        self.logger = logging.getLogger("error")
        handler = logging.FileHandler(filename=GO2ERRORS, mode='w')
        handler.setFormatter(logging.Formatter('%(levelname)s %(asctime)-15s %(message)s'))
        self.logger.addHandler(handler)
        self.were_errors = False

    def error(self, msg):
        self.logger.error(msg)
        self.were_errors = True

errorlog = MyLogger()


class Go2Exception(Exception):
    def __str__(self):
        return repr(self)


class PathError(Exception):
    pass


class PathItem(object):
    def __init__(self, path, level=0):
        assert isinstance(path, str)

        self.path = path
        self.level = level

    def __eq__(self, other):
        return self.path == other.path and self.level == other.level


def go2setup():
    bashrc = os.path.join(USERDIR, '.bashrc')
    open_flags = 'a'

    try:
        if ACTIVATION_CMD in config.fs.getcontents(bashrc):
            print('go2 already configured, skipping.')
            return 1

    except ResourceNotFoundError:
        open_flags = 'w'

    with config.fs.open(os.path.join(USERDIR, '.bashrc'), open_flags) as fd:
        fd.write("{0}\n{1}\n".format(ACTIVATION_CMD, CD_MODE_CMD))
        print('Setting up go2. It will be ready in next shell session.')


def rprint(text=''):
    sys.stdout.write("\r{0}".format(text))
#    sys.stdout.flush()


def message(text):
    rprint("({0})\r\n".format(text))


def high(text):
    return config.before + text + config.after


def abbreviate_home_prefix(path):
    return re.sub('^{0}'.format(USERDIR), '~', path)


def high_pattern_formatter(index, path, suffix):
    path = config.matcher.high_pattern(path)
    path = abbreviate_home_prefix(path)
    return '\r{0:c}: {1}{2}\r\n'.format(index, path, suffix)


class ListUniq(list):
    def append(self, item):
        if item in self:
            return

        list.append(self, item)

    def extend(self, other):
        for item in other:
            self.append(item)


class MatchLevel:
    NO_MATCH = -1
    START = 0
    START_IGNORECASE = 1
    CONTAIN = 2
    CONTAIN_IGNORECASE = 3


class PathMatcher(object):
    def __init__(self, pattern):
        self.pre_compute(pattern)

    def pre_compute(self, pattern):
        self.re_start = self.pattern2re_start(pattern)
        self.re_contain = self.pattern2re_contain(pattern)
        self.test_pattern(pattern)

    def test_pattern(self, pattern):
        try:
            re.match(self.re_start, "")
        except re.error:
            self.pre_compute([re.escape(x) for x in pattern])

    def match(self, path):
        if re.match(self.re_start, path, re.UNICODE):
            return MatchLevel.START

        if re.match(self.re_start, path, re.UNICODE | re.IGNORECASE):
            return MatchLevel.START_IGNORECASE

        if re.match(self.re_contain, path, re.UNICODE):
            return MatchLevel.CONTAIN

        if re.match(self.re_contain, path, re.UNICODE | re.IGNORECASE):
            return MatchLevel.CONTAIN_IGNORECASE

        return MatchLevel.NO_MATCH

    @staticmethod
    def pattern2re_start(pattern):
        return str.join('', ['.*/({0})[^/]*'.format(x) for x in pattern]) + '$'

    @staticmethod
    def pattern2re_contain(pattern):
        return str.join('', ['.*/.*({0})[^/]*'.format(x) for x in pattern]) + '$'

    def high_pattern(self, path):
        retval = ''
        begin = 0

        mo = re.match(self.re_contain, path, re.IGNORECASE)
        if mo is None:
            return path

        for i in range(1, mo.lastindex + 1):
            retval += mo.string[begin:mo.start(i)]
            retval += config.before + mo.group(i) + config.after
            begin = mo.end(i)

        retval += mo.string[begin:]
        return retval


def save_target(path):
    config.fs.setcontents(GO2TMP, path)


class PathFileStore:
    "Manage a file holding a path set"

    def __init__(self, path, size=1000):
        self.path = path
        self.size = size
        self.data = {}
        self.load()
        # self.log = logging.getLogger('PathFileStore [%s]' % os.path.split(path)[-1])

    def load(self):
        try:
            with config.fs.open(self.path) as fd:
                self._load_file_lines(fd)

        except ResourceNotFoundError:
            pass

    def _load_file_lines(self, fd):
        def decode(path):
            return path.strip()

        for line in fd:
            line = line.strip()
            if not line:
                continue

            try:
                visits, path = line.split(':', 1)
            except ValueError:
                visits, path = 1, line

            try:
                self.data[decode(path)] = int(visits)
            except UnicodeDecodeError:
                continue

    def __iter__(self):
        def _cmp(p1, p2):
            retval = -cmp(p1[1], p2[1])  # visits
            if retval == 0:
                return cmp(p1[0], p2[0])  # names

            return retval

        def _key(p):
            return -p[1], p[0]

#       FIXME: python3 sorted has not "cmp"
        for path, visits in sorted(list(self.data.items()), key=_key):
            yield path

    def add_visit_seq(self, seq, add_priority=1, set_priority=None):
        assert isinstance(seq, list)
        for path in seq:
            self.add_visit(path, add_priority, set_priority)
        return self

    def add_visit(self, path, add_priority=1, set_priority=None):
        assert isinstance(path, str), path
        if set_priority is not None:
            self.data[path] = set_priority
        else:
            visits = self.data.get(path, 0)
            self.data[path] = visits + add_priority
        return self

    def save(self):
        with config.fs.open(self.path, 'w') as fd:
            for path, visits in list(self.data.items())[:self.size]:
                line = "{0}:{1}\n".format(visits, path)
                fd.write(line)

    def __repr__(self):
        return "<PathFileStore '{0}'>".format(self.path)


def save_in_history(path, inc_priority):
    PathFileStore(GO2HISTORY).add_visit(path, inc_priority).save()


def from_file_provider(path_store):
    for path in path_store:
        level = config.matcher.match(path)
        if level == MatchLevel.NO_MATCH:
            continue

        if not config.fs.isdir(path):
            del path_store.data[path]
            continue

        yield PathItem(path, level)


class CommandProvider:
    def __init__(self, command):
        self.command = command

        self.ps = subp.Popen(
            shlex.split(command),
            bufsize    = 0,
            shell      = False,
            close_fds  = True,
            stdout     = subp.PIPE,
            # stderr     = subp.PIPE,
            preexec_fn = os.setsid)

        logging.info('%s: starts', self)

        self.abort = False
        signal.signal(signal.SIGTERM, self.terminate)

    def is_alive(self):
        value = os.waitpid(self.ps.pid, os.WNOHANG)
        logging.debug('%s: waitpid %s ', self, value)
        return value == (0, 0)

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

        except OSError as e:
            logging.error('%s: %s', self, e)

        # WARN: This kills the worker running this provider
        sys.exit()

    def __iter__(self):
        try:
            for path in self.ps.stdout:
                if self.abort:
                    return

                path = path.strip().decode()

                try:
                    self.path_sanity_check(path)
                except PathError as e:
                    yield e

                level = config.matcher.match(path)
                if level == MatchLevel.NO_MATCH:
                    continue

                if not config.fs.isdir(path):
                    continue

                yield PathItem(path, level)

        except IOError:
            self.terminate()

    def path_sanity_check(self, path):
        pass

    def __str__(self):
        return "CommandProvider pid:{0} cmd:'{1}'".format(self.ps.pid, self.command)


class TreeProvider(CommandProvider):
    def __init__(self, path):
        assert os.path.isabs(path)
        assert config.fs.isdir(path)
        self.path = path
        self.command = 'tree -dfin --noreport "{}"'.format(path)
        super(TreeProvider, self).__init__(command=self.command)

    def path_sanity_check(self, path):
        errormsg = "[error opening dir]"
        if errormsg not in path:
            return

        msg = "'{}' {}".format(self.command, path)
        raise PathError(msg)
#        logging.error(msg)
#        errorlog.error(msg)
        print("--> %s" % errorlog.were_errors)


def walk_provider(path):
    print('walk_provider')
    assert os.path.isabs(path)
    assert config.fs.isdir(path)

    for root, dirnames, filenames in os.walk(path):
        paths = [os.path.join(root, x) for x in dirnames
                 if not x.startswith('.')]

        for path in paths:
            # FIXME: refactor this, is repeated in all providers
            level = config.matcher.match(path)
            if level == MatchLevel.NO_MATCH:
                continue

            if not config.fs.isdir(path):
                continue

            yield PathItem(path, level)


class CancelException(Go2Exception):
    pass


class NotMatchException(Go2Exception):
    pass


class NotExistsException(Go2Exception):
    pass


class NothingToDoException(Go2Exception):
    pass


class TTY:
    def __init__(self):
        self.old_settings = tty.tcgetattr(sys.stdin)

    def set_raw(self):
        tty.setraw(sys.stdin)

    def restore(self):
        tty.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)


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
            self.push(func(*args))
            self.tasks.task_done()

        self.tasks.task_done()

    def push(self, source):
        if source is None:
            return

        try:
            for x in source:
                self.output.put(x)
        except TypeError as e:
            print_exc()
            # print("TypeError %s" % e)
            # self.output.put(e)


class TaskQueue(mp_queues.JoinableQueue):
    def unfinished_tasks_count(self):
        return self._unfinished_tasks._semlock._get_value()


class ProcessPool(object):
    def __init__(self, num_workers=None):
        try:
            try:
                self.task_queue = TaskQueue()
            except TypeError:
                self.task_queue = TaskQueue(ctx=mp)
        except OSError as e:
            message(str(e))
            message("See http://goo.gl/a1hhU0")

        self.output_queue = mp.Queue()

        num_workers = num_workers or mp.cpu_count()
        self.workers = [Worker(self.task_queue, self.output_queue)
                        for x in range(num_workers)]

    def add_task(self, func, *args):
        logging.info('new task for: %s%s', func.__name__, args)
        self.task_queue.put((func, args))

    def sleep_free_workers(self, seconds):
        for i in range(len(self.workers) - self.task_queue.unfinished_tasks_count()):
            self.add_task(time.sleep, seconds)

    def has_tasks(self):
        time.sleep(0.1)
        return self.task_queue.unfinished_tasks_count() != 0

    def terminate(self):
        if not any(w.is_alive() for w in self.workers):
            return

        logging.debug('pool: terminating')

        for w in self.workers:
            self.task_queue.put(STOP)

        time.sleep(0.1)

        for w in self.workers:
            if w.is_alive():
                w.terminate()

        logging.debug('pool: terminated')

    def join(self):
        while self.has_tasks():
            time.sleep(0.1)

#        self.terminate()


class QueueExtractor(object):
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, fd, condition, queue, *args):
        event = queue.get()

        self.callback(event)
        return True


class QueueReactor(object):
    class Callback(object):
        def __init__(self, reactor, func):
            self.reactor = reactor
            self.func = func

        def __call__(self, *args):
            try:
                return self.func(*args)

            except Exception as e:
                if not isinstance(e, Go2Exception):
                    print_exc()

                logging.warning('{0!r}: {1}'.format(self.reactor, e))
                self.reactor.exception = e
                self.reactor.quit()
                return False

    def __init__(self):
        self.mainloop = GLib.MainLoop()
        self.context = self.mainloop.get_context()
        self.at_quit_func = lambda: None
        self.exception = None

    def queue_add_watch(self, queue, func, *args):
        GLib.io_add_watch(
            queue._reader, GLib.IO_IN,
            self.Callback(self, func), queue, *args,
            priority=GLib.PRIORITY_HIGH)

    def io_add_watch(self, fd, func, *args):
        GLib.io_add_watch(
            fd, GLib.IO_IN,
            self.Callback(self, func), *args)

    def timeout_add(self, t, func, *args):
        GLib.timeout_add(t, self.Callback(self, func), *args)

    def at_quit(self, func):
        self.at_quit_func = func

    def process_pending(self):
        time.sleep(0.1)
        while self.context.pending():
            self.context.iteration()

    def iteration(self):
        time.sleep(0.1)
        self.context.iteration()

    def run(self):
        # time.sleep(0.1)
        self.mainloop.run()
        self.at_quit_func()
        if self.exception is not None:
            raise self.exception

    def quit(self):
        logging.debug('reactor quit')
        self.mainloop.quit()

    def __repr__(self):
        return self.__class__.__name__


class PathBuffer(object):
    def __init__(self, sink=None):
        self.sink = sink
        self.groups = [list() for x in range(4)]
        self.filters = []

    def set_sink(self, sink):
        self.sink = sink

    def add(self, path_item):
        if path_item is None:
            return True

        try:
            self._tryTo_add(path_item)
        except Sink.FullSinkException:
            return False

        return True

    def _tryTo_add(self, item):
        # print '\r', repr(item.path)
        # print '\r', self.groups[item.level]

        if isinstance(item, PathError):
            errorlog.error(str(item))
            return

        if item.path in self.groups[item.level] or \
                any(f(item.path) for f in self.filters):
            return

        self.groups[item.level].append(item.path)

        if item.level == MatchLevel.START:
            self.sink.add_entry(item.path)

    def add_filter(self, f):
        self.filters.append(f)

    def flush_alternate(self):

        def add_paths_of_group(group):
            for path in group:
                self.sink.add_entry(path)

        try:
            for level in range(1, 4):
                if not self.groups[level]:
                    continue

                if level != 3:
                    self.sink.next_group()

                add_paths_of_group(self.groups[level])

        except Sink.FullSinkException:
            return


class Sink(object):
    class FullSinkException(Go2Exception):
        pass

    class InvalidChoiceException(Go2Exception):
        pass

    def add_entry(self, path):
        raise NotImplementedError

    def next_group(self):
        pass


class PrintSink(Sink):
    def add_entry(self, path):
        rprint(path + '\n\r')


class Menu(Sink):
    def __init__(self, reactor, out, max_size=26):
        self.reactor = reactor
        self.fd = out
        self.max_size = max_size
        self.entries = []
        self.is_full = False
        self.target = None
        self.formatter = self.default_formatter

    def perform_choice(self, choice):
        if not self.is_valid_choice(choice):
            raise self.InvalidChoiceException()

        logging.debug("choice: {0}, entries: {1}".format(
                      choice, self.entries))

        self.target = self.entries[choice]
        self.reactor.quit()

    def is_valid_choice(self, choice):
        return choice in range(0, len(self.entries))

    def next_group(self):
        self.out_write('\r   ---        \n')

    def add_entry(self, entry):
        assert isinstance(entry, str)

        if len(self.entries) >= self.max_size:
            self.is_full = True
            raise self.FullSinkException

        self.entries.append(entry)
        self.write_last()

    def write_last(self):
        suffix = ''
        if len(self.entries) == 1:
            suffix += ' [ENTER]'

        line = self.formatter(
            len(self.entries) + ord('a') - 1,
            self.entries[-1],
            suffix)

        self.out_write(line)

    def default_formatter(self, index, path, suffix):
        return '{0:c}: {1}'.format(index, path)

    def out_write(self, text):
        try:
            self.fd.write(text)
        except UnicodeEncodeError as e:
            print("out_write {}".format(e))
            print(repr(text))

        self.fd.flush()


def user_break_checker(key):
    if key in [ESC, CTRL_C]:
        raise CancelException


class UserInputHandler(object):
    def __call__(self, fd, condition=None):
        key = ord(fd.read(1))
        user_break_checker(key)
        return True


class UserChoiceHandler(object):
    def __init__(self, sink):
        self.sink = sink

    def __call__(self, fd, condition=None):
        key = ord(fd.read(1))
        user_break_checker(key)

        try:
            choice = self.key2choice(key)
            self.sink.perform_choice(choice)
        except Sink.InvalidChoiceException:
            return True

        return False

    def key2choice(self, key):
        if key == ENTER:
            return 0

        return key - ord('a')


class IgnoreManager(object):
    def __init__(self, content):
        self.patterns = []
        for line in content.split():
            line = line.strip()
            if os.sep not in line:
                line = '*/{0}/*'.format(line)

            self.patterns.append(line)

    @classmethod
    def from_file(cls, fname):
        return IgnoreManager(config.fs.getcontents(fname))

    def is_ignored(self, path):
        assert path.startswith(os.sep), "It must be an absolute path"

        path = os.path.normpath(path) + os.sep

        retval = any(fnmatch(path, x) for x in self.patterns)
        if retval:
            logging.debug("Ignored: %s", path)

        return retval


class Go2Base:
    def __init__(self):
        self.pool = ProcessPool()
        self.reactor = QueueReactor()
        self.path_buffer = PathBuffer()

        self.setup_stdin()

        self.setup_ignore()
        self.reactor.queue_add_watch(self.pool.output_queue,
                                     QueueExtractor(self.path_buffer.add))

    def setup_stdin(self):
        stdin_tty = TTY()
        stdin_tty.set_raw()
        atexit.register(stdin_tty.restore)

    def setup_ignore(self):
        try:
            ignore_manager = IgnoreManager.from_file(GO2IGNORE)
            self.path_buffer.add_filter(ignore_manager.is_ignored)
        except ResourceNotFoundError:
            pass

    def stop(self, *args):
        self.pool.terminate()

    def run(self):
        retval = 1
        self.history = PathFileStore(GO2HISTORY)
        self.cache = PathFileStore(GO2CACHE)

        self.create_tasks()
        self.reactor.timeout_add(250, self.end_checker)

        try:
            self.reactor.run()
            self.on_success()
            retval = 0

        except CancelException:
            message("canceled by user")
        except NotMatchException:
            message("pattern not found")

        self.pool.terminate()
        return retval

    def create_tasks(self):
        self.create_file_tasks()
        self.pool.join()
        self.create_command_tasks()

    def create_file_tasks(self):
        self.pool.add_task(from_file_provider, self.history)
        self.pool.sleep_free_workers(0.1)
        self.pool.add_task(from_file_provider, self.cache)

    def not_overlapped_history(self):
        history_paths = []
        for p in sorted(list(self.history.data.keys()), key=len):
            if any(p.startswith(x) for x in history_paths):
                continue

            history_paths.append(p)

        # print str.join('\r\n', history_paths)
        return history_paths

    def create_command_tasks(self):
        paths = ListUniq(config.search_path.split(':'))
        # paths.extend(self.not_overlapped_history())

        for path in set(paths):
            path = os.path.abspath(path)
            if not config.fs.isdir(path):
                message("'{0}' does not exist".format(path))

            # print("add task: " + path)
            # self.pool.add_task(walk_provider, path)
            self.pool.add_task(TreeProvider, path)

    def end_checker(self):
        return False

    def on_success(self):
        pass


class Go2Interactive(Go2Base):
    def __init__(self):
        Go2Base.__init__(self)
        self.setup_stdout()

        self.menu = Menu(self.reactor, sys.stdout)
        self.menu.formatter = high_pattern_formatter
        self.path_buffer.set_sink(self.menu)

        self.reactor.io_add_watch(sys.stdin, UserChoiceHandler(self.menu))

        self.progress = cycle(list(range(4)))

    def setup_stdout(self):
        def stdout_restore():
            sys.stdout = sys.__stdout__

        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w')
        atexit.register(stdout_restore)

    def end_checker(self):
        if self.menu.is_full:
            message("warning: too many matches!")
            self.on_end()
            rprint("Select path: ")
            self.pool.terminate()
            return False

        if self.pool.has_tasks():
            rprint("\rSearching{0:3} ".format('.' * next(self.progress)))
            return True

        self.path_buffer.flush_alternate()

        if len(self.menu.entries) == 0:
            self.on_end()
            raise NotMatchException

        if len(self.menu.entries) == 1:
            message("single match")
            self.on_end()
            self.menu.perform_choice(0)
            return False

        rprint("Select path: ")
        return False

    def on_success(self):
        rprint("Changing to: {0}\r\n".format(
               high(abbreviate_home_prefix(self.menu.target))))

        save_target(self.menu.target)

        self.history.add_visit(self.menu.target).save()
        logging.debug("saved history %s", len(self.menu.entries))

        self.cache.add_visit_seq(self.menu.entries, set_priority=1).save()

    def on_end(self):
        if errorlog.were_errors:
            message("there were errors. See '{}'".format(GO2ERRORS))


class Go2ListOnly(Go2Base):
    def __init__(self):
        Go2Base.__init__(self)
        self.path_buffer.set_sink(PrintSink())
        self.reactor.io_add_watch(sys.stdin, UserInputHandler())

    def end_checker(self):
        if not self.pool.has_tasks():
            self.reactor.quit()

        return True


def create_directory_wizzard(path):

    def show_make_and_change(path):
        path = os.path.abspath(path)
        path = config.matcher.high_pattern(path)
        path = abbreviate_home_prefix(path)
        print(("go2: Making and changing to directory: %s" % path))

    if path.startswith(CWD):
        path = os.path.abspath(path)[len(CWD):].strip('/')

    print("go2: '{}' does not exist.\n(c)ancel, (s)earch or (m)ake? (C/s/m):".format(path), end=" ")

    try:
        answer = input().lower()
    except KeyboardInterrupt:
        answer = ''
        print

    if len(answer) != 1 or answer not in 'sm':
        message('canceled')
        return 1

    if answer == 'm':
        try:
            config.fs.makedir(path, recursive=True)
        except OSError as e:
            print(e)
            sys.exit(1)

        show_make_and_change(path)
        save_in_history(path, 10)
        save_target(path)
        return 0

    # search
    Go2Interactive().run()


def chdir_decorator(wizzard=False):
    if not config.pattern:
        save_target(USERDIR)
        return 0

    params = str.join(' ', config.pattern)
    vip_path = params.endswith(os.sep * 2)

    try:
        target = os.path.abspath(params)
    except (IOError, OSError, FileNotFoundError) as e:
        message("Current directory does not exists")
        logging.error(e)
        save_target(USERDIR)
        return 0

    if params == '-':
        save_target('-')
        return 0

    if config.fs.isdir(target):
        save_in_history(target, 200 if vip_path else 50)
        save_target(target)
        return 0

    raise NotExistsException(target)


def get_config(args=None):
    args = args or []

    encoding = locale.getdefaultlocale()[1]

    parser = argparse.ArgumentParser(
        prog = 'go2',
        description = DESCRIPTION,
        epilog = '.',
        formatter_class = argparse.RawDescriptionHelpFormatter)

    parser.add_argument('pattern', nargs='*', help="pattern to find")
    parser.add_argument('--cd', dest='chdir', action="store_true",
                        help="'cd' alias with caching")
    parser.add_argument('-i', '--ignore-case', dest='ignorecase',
                        action='store_true', default=False,
                        help="ignore case search")
    parser.add_argument('-l', '--list-only', dest='listonly', action='store_true',
                        help="list matches and exit")
    parser.add_argument('-p', '--path', metavar='PATH', dest='search_path',
                        default="{0}:{1}".format(CWD, USERDIR),
                        help='set search path (default: "./:{0}")'.format(USERDIR))
    parser.add_argument('-r', '--from-root', dest='from_root',
                        action='store_true',
                        help="add / to the search path")
    parser.add_argument('-v', '--version', action='version',
                        version='%(prog)s ' + __version__ = '2.20181225.7'
    parser.add_argument('--setup',
                        action='store_true',
                        help="install go2 in your .bashrc")

    retval = parser.parse_args(args)
    retval.parser = parser

    retval.engine = Go2ListOnly if retval.listonly else Go2Interactive

    retval.encoding = encoding

    # process args
    if retval.ignorecase:
        retval.pattern = [x.lower() for x in retval.pattern]

    if retval.from_root:
        retval.search_path += ':/'

    # application globals
    retval.matcher = PathMatcher(retval.pattern)

    retval.fs = OSFS('/')
    retval.fs.makedir(GO2DIR, allow_recreate=True)

    retval.before = HIGH
    retval.after = LOW

    return retval


def is_an_actual_dir():
    return len(config.pattern) == 1 and config.pattern[0][-1] == os.sep and config.fs.isdir(config.pattern[0])


if __name__ == '__main__':
    config = get_config(sys.argv[1:])

    if config.setup:
        sys.exit(go2setup())

    if config.chdir or is_an_actual_dir():
        try:
            sys.exit(chdir_decorator())
        except NotExistsException as target:
            sys.exit(create_directory_wizzard(target.args[0]))

    if not config.pattern:
        print("(go2) error: too few arguments\n")
        config.parser.print_help()
        sys.exit(1)

    engine = config.engine()

    signal.signal(signal.SIGINT, engine.stop)
    sys.exit(engine.run())
