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

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

try:
    sys.path.remove(os.getcwd())
except (OSError, ValueError):
    pass

#os.environ['LANG'] = 'C'

import pwd
import tty
import termios
import time
import signal
import re
import logging
import locale

from threading import Thread
import multiprocessing as mp
import multiprocessing.queues as mp_queues
import subprocess as subp
import shlex
from traceback import print_exc
from itertools import cycle

import gobject
import argparse
from osfs import OSFS, ResourceNotFoundError

ESC = 27
CTRL_C = 3
ENTER = 13
HIGH = chr(27) + '[1m'
LOW  = chr(27) + '[m'


USERDIR    = os.environ['HOME']
GO2DIR     = os.path.join(USERDIR, '.go2')
GO2IGNORE  = os.path.join(GO2DIR, 'ignore')
GO2HISTORY = os.path.join(GO2DIR, 'history')
GO2CACHE   = os.path.join(GO2DIR, 'cache')
#GO2CONFIG  = os.path.join(GO2DIR, 'config')
GO2TMP     = os.path.join(GO2DIR, 'tmp')
GO2LOG     = os.path.join(GO2DIR, 'log')

VERSION = '1.20111224'

ACTIVATION_CMD = "[ -e /usr/lib/go2/go2.sh ] && source /usr/lib/go2/go2.sh"
CD_MODE_CMD = "alias cd='go2 --cd'"

STOP = 'STOP'


logging.basicConfig(
    filename=os.path.join('/tmp/go2-%s' % pwd.getpwuid(os.getuid())[0]),
    filemode='w',
    format='%(asctime)-15s %(message)s',
    level=logging.DEBUG)


def to_unicode(text, encoding=None):
    encoding = encoding or config.encoding

    if isinstance(text, unicode):
        return text

    return unicode(text, encoding=encoding, errors='replace')


class Go2Exception(Exception):
    def __str__(self):
        return repr(self)


class PathItem:
    def __init__(self, path, level=0):
        self.path = to_unicode(path)
        self.level = level

    def __eq__(self, other):
        return self.path == other.path and self.level == other.level


def go2setup(mode='r+'):
    try:
        if ACTIVATION_CMD in config.fs.getcontents(
            os.path.join(USERDIR, '.bashrc')):
            print('go2 already configured, skipping.')
            return 1

    except ResourceNotFoundError:
        pass

    with config.fs.open(os.path.join(USERDIR, '.bashrc'), 'w') as fd:
        fd.write("{0}\n{1}\n".format(ACTIVATION_CMD, CD_MODE_CMD))
        print('Setting up go2. It will be ready in next shell session.')


def rprint(text=''):
    sys.stdout.write("\r{0}".format(text.encode(config.encoding)))
    sys.stdout.flush()


def message(text):
    rprint("({0})\n".format(text))


def high(text):
    return config.before + text + config.after


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


def abbreviate_home_prefix(path):
    return re.sub(u'^{0}'.format(USERDIR), '~', path)


def highpath_formatter(index, path, suffix):
    path = high_pattern(config.pattern, path)
    path = abbreviate_home_prefix(path)
    return u'\r{0:c}: {1}{2}\r\n'.format(index, path, suffix)


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


def pattern2re_start(pattern):
    return unicode.join(u'', [u'.*/({0})[^/]*'.format(x) for x in pattern]) + u'$'


def pattern2re_contain(pattern):
    return unicode.join(u'', [u'.*/.*({0})[^/]*'.format(x) for x in pattern]) + u'$'


# FIXME: precompute RE
def match(path):
    re_str = pattern2re_start(config.pattern)
#    print re_str, path
#    print type(re_str), type(path)
    if re.match(re_str, path, re.UNICODE):
        return MatchLevel.START

    if re.match(re_str, path, re.UNICODE | re.IGNORECASE):
        return MatchLevel.START_IGNORECASE

    re_str = pattern2re_contain(config.pattern)
    if re.match(re_str, path, re.UNICODE):
        return MatchLevel.CONTAIN

    if re.match(re_str, path, re.UNICODE | re.IGNORECASE):
        return MatchLevel.CONTAIN_IGNORECASE

    return MatchLevel.NO_MATCH


def save_target(path):
    config.fs.setcontents(GO2TMP, path.encode(config.encoding))


class PathFileStore:
    "Manage a file holding a path set"

    def __init__(self, path, size=1000):
        self.path = path
        self.size = size
        self.data = {}
        self.load()
#        self.log = logging.getLogger('PathFileStore [%s]' % os.path.split(path)[-1])

    def load(self):
        try:
            with config.fs.open(self.path) as fd:
                self._load_file_lines(fd)

        except ResourceNotFoundError:
            pass

    def _load_file_lines(self, fd):
        def decode(path):
            return path.strip().decode('utf8')

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
            retval = -cmp(p1[1], p2[1])
            if retval == 0:
                return cmp(p1[0], p2[0])

            return retval

        for path, visits in sorted(self.data.items(), cmp=_cmp):
            yield path

    def add_visit_seq(self, seq):
        assert isinstance(seq, list)
        for path in seq:
            self.add_visit(path)
        return self

    def add_visit(self, path):
        assert isinstance(path, unicode), path
        visits = self.data.get(path, 0)
        self.data[path] = visits + 1
        return self

    def save(self):
#        print "=", self.data
        with config.fs.open(self.path, 'w') as fd:
            for path, visits in self.data.items()[:self.size]:
                line = u"{0}:{1}\n".format(visits, path)
                fd.write(line.encode('utf8'))

    def __unicode__(self):
        return "<PathFileStore {0}>".format(self.path)


def save_in_history(path):
    PathFileStore(GO2HISTORY).add_visit(path).save()


def from_file_provider(path_store):
    for path in path_store:
        level = match(path)
        if level == MatchLevel.NO_MATCH:
            continue

        if not config.fs.exists(path):
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
            stderr     = subp.PIPE,
            preexec_fn = os.setsid)

        logging.info('%s: starts', self)

        self.abort = False
        signal.signal(signal.SIGTERM, self.terminate)

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

        # WARN: This kills the worker running this provider
        sys.exit()

    def __iter__(self):
        try:
            for path in self.ps.stdout:
                if self.abort:
                    return

                path = path.strip()

                level = match(path)
                if level == MatchLevel.NO_MATCH:
                    continue

                if not config.fs.exists(path):
                    continue

                yield PathItem(path, level)

        except IOError:
            self.terminate()

    def __str__(self):
        return "CommandProvider pid:{0} cmd:'{1}'".format(self.ps.pid, self.command)


def tree_provider(root):
    return CommandProvider('tree -dfin --noreport %s' % root)


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
        try:
            for x in source:
                self.output.put(x)
        except TypeError:
            self.output.put(source)


class TaskQueue(mp_queues.JoinableQueue):
    def unfinished_tasks_count(self):
        return self._unfinished_tasks._semlock._get_value()


class ProcessPool(object):
    def __init__(self, num_workers=None):
        self.task_queue = TaskQueue()
        self.output_queue = mp.Queue()

        num_workers = num_workers or mp.cpu_count()
        self.workers = [Worker(self.task_queue, self.output_queue)
                        for x in range(num_workers)]

    def add_task(self, func, *args):
        self.task_queue.put((func, args))

    def sleep_free_workers(self, seconds):
        for i in range(len(self.workers) - self.task_queue.unfinished_tasks_count()):
            self.add_task(time.sleep, seconds)

    def has_tasks(self):
        return self.task_queue.unfinished_tasks_count() != 0

    def terminate(self):
        if not any(w.is_alive() for w in self.workers):
            return

        logging.debug('pool: terminating')

        for w in self.workers:
            self.task_queue.put(STOP)

        time.sleep(0.1)

#        term_threads = [ThreadStarted(target=w.terminate) for w in self.workers
#                        if w.is_alive()]
#
#        for t in term_threads:
#            t.join()

        for w in self.workers:
            if w.is_alive():
                w.terminate()

        logging.debug('pool: terminated')

    def join(self):
        while self.has_tasks():
            time.sleep(0.1)

        self.terminate()


class QueueExtractor(object):
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, fd, condition, queue, *args):
        event = queue.get()

        self.callback(event)
        return True


class QueueReactor(gobject.MainLoop):
    class Callback(object):
        def __init__(self, reactor, func):
            self.reactor = reactor
            self.func = func

        def __call__(self, *args):
            try:
                return self.func(*args)

            except Exception, e:
                if not isinstance(e, Go2Exception):
                    print_exc()

                logging.warning('{0!r}: {1}'.format(self.reactor, e))
                self.reactor.exception = e
                self.reactor.quit()
                return False

    def __init__(self):
        gobject.MainLoop.__init__(self)
        self.context = self.get_context()
        self.at_quit_func = lambda: None
        self.exception = None

    def queue_add_watch(self, queue, func, *args):
        gobject.io_add_watch(
            queue._reader, gobject.IO_IN,
            self.Callback(self, func), queue, *args,
            priority=gobject.PRIORITY_HIGH)

    def io_add_watch(self, fd, func, *args):
        gobject.io_add_watch(
            fd, gobject.IO_IN,
            self.Callback(self, func), *args)

    def timeout_add(self, t, func, *args):
        gobject.timeout_add(t, self.Callback(self, func), *args)

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
        time.sleep(0.1)
        gobject.MainLoop.run(self)
        self.at_quit_func()
        if self.exception is not None:
            raise self.exception

    def quit(self):
        logging.debug('reactor quit')
        gobject.MainLoop.quit(self)


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
#        print '\r', repr(item.path)
#        print '\r', self.groups[item.level]

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

    def add_entry(self, path):
        raise NotImplementedError

    def next_group(self):
        pass


class PrintSink(Sink):
    def add_entry(self, path):
        print path


class Menu(Sink):

    class InvalidChoiceException(Go2Exception):
        pass

    def __init__(self, reactor, out, max_size=26):
        self.reactor = reactor
        self.fd = out
        self.max_size = max_size
        self.entries = []
        self.is_full = False
        self.target = None
        self.formatter = self.default_formatter

    def input_handler(self, fd, condition=None):
        key = ord(fd.read(1))
#        key = os.read(fd, 1)
#        print key

        if key in [ESC, CTRL_C]:
            raise CancelException

        try:
            choice = self.key2choice(key)
            logging.debug("choice: {0}, entries: {1}".format(
                    choice, self.entries))
        except self.InvalidChoiceException:
            return True

        self.perform_choice(choice)
        return False

    def key2choice(self, key):
        if key == ENTER:
            choice = 0
        else:
            choice = key - ord('a')

        if not self.is_valid_choice(choice):
            raise self.InvalidChoiceException()

        return choice

    def is_valid_choice(self, choice):
        return choice in range(0, len(self.entries))

    def perform_choice(self, choice):
        self.target = self.entries[choice]
        self.reactor.quit()

    def next_group(self):
        self.out_write('\r   ···        \n')

    def add_entry(self, entry):
        if len(self.entries) >= self.max_size:
            self.is_full = True
            raise self.FullSinkException

        self.entries.append(to_unicode(entry))
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
        self.fd.write(text)
        self.fd.flush()


class IgnoreManager(object):
    def __init__(self, content):
        self.ignored_names = [x.strip() for x in content.split()]

    @classmethod
    def from_file(cls, fname):
        return IgnoreManager(config.fs.getcontents(fname))

    def is_ignored(self, path):
        assert path.startswith(os.sep), "It must be an absolute path"
        retval = any(x in self.ignored_names for x in path.split(os.sep))
        if retval:
            logging.debug("Ignored: %s", path)
        return retval


class Go2Base(object):
    def __init__(self):
        self.pool = ProcessPool()
        self.reactor = QueueReactor()
        self.path_buffer = PathBuffer()

        self.setup_ignore()

        self.reactor.queue_add_watch(self.pool.output_queue,
                                     QueueExtractor(self.path_buffer.add))

    def setup_ignore(self):
        try:
            ignore_manager = IgnoreManager.from_file(GO2IGNORE)
            self.path_buffer.add_filter(ignore_manager.is_ignored)
        except ResourceNotFoundError:
            pass

    def run(self):
        retval = 1
        self.history = PathFileStore(GO2HISTORY)
        self.cache = PathFileStore(GO2CACHE)

        self.create_tasks()

        try:
            self.reactor.run()
            self.on_success()
            retval = 0

        except CancelException:
            message(u"canceled by user")
        except NotMatchException:
            message(u"pattern not found")

        self.pool.terminate()
        return retval

    def create_tasks(self):
        self.pool.add_task(from_file_provider, self.history)
        self.pool.sleep_free_workers(seconds=1)

        self.pool.add_task(from_file_provider, self.cache)

        paths = ListUniq()
        paths.extend([os.getcwd(), USERDIR])
#        paths.extend(self.not_overlapped_history())

        if config.from_root:
            paths.append('/')

        for path in paths:
            if not config.fs.isdir(path):
                message("'{0}' does not exist".format(path))

            self.pool.add_task(tree_provider, path)

    def on_success(self):
        pass


class Go2Interactive(Go2Base):
    def __init__(self):
        Go2Base.__init__(self)
        self.menu = Menu(self.reactor, sys.stdout)
        self.menu.formatter = highpath_formatter
        self.path_buffer.set_sink(self.menu)
        self.tty = TTY()

        self.tty.set_raw()
        self.reactor.io_add_watch(sys.stdin, self.menu.input_handler)
        self.reactor.timeout_add(250, self.end_checker)
        self.reactor.at_quit(self.tty.restore)

        self.progress = cycle(range(4))

    def end_checker(self):
        if self.menu.is_full:
            message(u"warning: too many matches!")
            rprint('Select path: ')
            self.pool.terminate()
            return False

        if self.pool.has_tasks():
            rprint(u"\rSearching{0:3} ".format('.' * self.progress.next()))
            return True

        self.path_buffer.flush_alternate()

        if len(self.menu.entries) == 0:
            raise NotMatchException

        if len(self.menu.entries) == 1:
            message(u"single match")
            self.menu.perform_choice(0)
            return False

        rprint(u"Select path: ")
        return False

    def on_success(self):
        rprint(u"Changing to: {0}\n".format(
                high(abbreviate_home_prefix(self.menu.target))))
        save_target(self.menu.target)

        self.history.add_visit(self.menu.target).save()

        logging.debug("Saved history %s", len(self.menu.entries))
        self.cache.add_visit_seq(self.menu.entries).save()


class Go2ListOnly(Go2Base):
    def __init__(self):
        Go2Base.__init__(self)
        self.path_buffer.set_sink(PrintSink())
        self.reactor.timeout_add(250, self.end_checker)

    def end_checker(self):
        if not self.pool.has_tasks():
            self.reactor.quit()

        return True


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

    # search
    Go2Interactive().run()


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


def get_config(args=None):
    args = args or []

    encoding = locale.getdefaultlocale()[1]

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
    parser.add_argument('--cwd', metavar='DIR', default=None,
                        help="change current directory to DIR")
    parser.add_argument('--cd', dest='chdir', action="store_true",
                        help="'cd' alias with caching")
    parser.add_argument('-i', '--ignore-case', dest='ignorecase',
                        action='store_true', default=False,
                        help="ignore case search")
    parser.add_argument('-l', '--list-only', dest='listonly', action='store_true',
                        help="list matches only")
    parser.add_argument('-r', '--from-root', dest='from_root',
                        action='store_true',
                        help="search in whole file system")
    parser.add_argument('--setup',
                        action='store_true',
                        help="install go2 in your .bashrc")
    parser.add_argument('--version', action='version', version='%(prog)s ' + VERSION)

    retval = parser.parse_args(args)
    retval.parser = parser

    retval.engine = Go2ListOnly if retval.listonly else Go2Interactive

    retval.encoding = encoding
    retval.pattern = [to_unicode(x, encoding) for x in retval.pattern]

    # process args
    if retval.ignorecase:
        retval.pattern = [x.lower() for x in retval.pattern]

#    retval.apply_case = str.lower if retval.ignorecase else str
#    print retval.pattern

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

    if config.cwd:
        try:
            os.chdir(config.cwd)
        except OSError:
            message("'{0}' does not exist".format(config.cwd))
            sys.exit(1)

    if not config.pattern:
        print("go2.py: error: too few arguments\n")
        config.parser.print_help()
        sys.exit(1)

    sys.exit(config.engine().run())
