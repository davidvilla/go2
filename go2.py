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

import multiprocessing as mp
import subprocess as subp
import Queue
import tty
import select
import termios
import time
import signal

import logging
log = logging.getLogger('2go')

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

VERSION = '1.20110805'


def go2setup():
    if os.system('grep go2.sh ~/.bashrc > /dev/null') == 0:
        print('go2 already configured, skipping.')
        return 1

    with open(os.path.join(USERDIR, '.bashrc', 'w')) as fd:
        fd.write('''
[ -e /usr/lib/go2/go2.sh ] && source /usr/lib/go2/go2.sh
alias cd='go2 --cd'
''')

    print('Setting up go2. It will be ready in next shell session.')
    return 0


def rprint(cad=''):
    sys.stdout.write('\r' + cad)
    sys.stdout.flush()


def high(text):
    return HIGH + text + LOW


def highlight_pattern(pattern, path):
    items = path.split(os.sep)

    p = len(pattern) - 1
    for i in range(len(items) - 1, -1, -1):
        if p < 0:
            break

        if config.apply_case(items[i]).startswith(config.apply_case(pattern[p])):
            orig = items[i][:len(pattern[p])]
            items[i] = items[i].replace(orig, high(orig), 1)
            p -= 1

    return os.sep.join(items)


def match_single(path):
    path = config.apply_case(path.strip('\n'))
    return os.path.basename(path).startswith(config.pattern[0])


def match_multi(path):
    path = config.apply_case(path.strip('\n'))

    pattern = config.pattern
    items = path.split(os.sep)[1:]

    match = items[-1].startswith(pattern[-1])
    if not match:
        return False

    p = len(pattern) - 2
    for i in items[-2::-1]:
        if p < 0:
            return True

        if i.startswith(pattern[p]):
            p -= 1

    return False


def loadlines(fname):
    if not os.path.exists(fname):
        return []

    try:
        with open(fname) as fd:
            return [x for x in [y.strip() for y in fd.readlines()] if x]
    finally:
        del fd


def savelines(fname, seq):
    if os.path.exists(fname):
        os.remove(fname)

    with open(fname, 'w') as fd:
        fd.write(str.join('\n', seq) + '\n')


def save_target(path):
#    print '-->', path
    with open(GO2TMP, 'w') as fd:
        fd.write(path)


class PathStore:
    "Manage a file holding a path set"
    def __init__(self, path, size=1000):
        self.path = path
        self.size = size
#        self.log = logging.getLogger('PathStore [%s]' % os.path.split(path)[-1])
        self.data = loadlines(path)

#        if not config.process_hidden:
#            self.data = filterout_hidden(self.data)

    def __iter__(self):
        for line in self.data[:]:
            yield line

    def insert(self, seq):
#        self.log.debug("   Saving to file: %s (%s)" % (item,
#                                                      str(len(self.data))))
        if isinstance(seq, str):
            seq = [seq]

        for item in seq:
            if item in self.data:
                self.data.remove(item)

            self.data.insert(0, item)

    def save(self):
        savelines(self.path, self.data[:self.size])

    def insert_and_save(self, item):
        self.insert(item)
        self.save()

    def __unicode__(self):
        return "<PathStore {0}>".format(self.path)


def save_in_history(path):
    PathStore(GO2HISTORY).insert_and_save(path)


def file_task(output, path_store):
    for path in path_store:
        if not config.match_func(path):
            continue

        if not os.path.exists(path):
            path_store.data.remove(path)
            continue

        output.put(path)


class CommandTask:
    def __init__(self, output, command):
        self.output = output
        self.ps = subp.Popen(command, shell=True, close_fds=True,
                        stdout=subp.PIPE, stderr=subp.PIPE,
                        preexec_fn = os.setsid)

        signal.signal(signal.SIGTERM, self.signal_handler)
        self.communicate()

    def signal_handler(self, signum, *args):
#        print self.ps, signum
        os.killpg(self.ps.pid, signum)
        self.ps.wait()
        sys.exit(1)

    def communicate(self):
        for path in self.ps.stdout:
            path = path.strip()

            if not config.match_func(path):
                continue

            if not os.path.exists(path):
                continue

            self.output.put(path)


def tree_task(output, root):
    CommandTask(output, "tree -dfin --noreport %s" % root)


class FullException(Exception):
    pass


class CancelException(Exception):
    pass


class NotMatchException(Exception):
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

    def __init__(self, pspoll):
        self.pspoll = pspoll
        self.index = 0
        self.paths = []
        self.insert_enabled = True

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
        poll = select.poll()
        poll.register(sys.stdin, select.POLLIN)

        while 1:
            self.refresh()

            keypress = poll.poll(500)
            if not keypress:
                continue

            key = ord(sys.stdin.read(1))
            election = self.key2election(key)

            if self.is_valid_election(election):
                return election

    def refresh(self):
        try:
            while 1:
                msg = self.pspoll.output_queue.get(timeout=0.1)

                if isinstance(msg, str) and self.insert_enabled:
                    self.insert_path(msg)

        except Queue.Empty:
            pass

        except FullException:
            self.insert_enabled = False
            rprint('Warning: Too many matches!\n')

        if self.pspoll.has_tasks() and self.insert_enabled:
            rprint('Searching... ' + str())
            return

        if not self.paths:
            raise NotMatchException

        rprint('Select a path: ')

    def key2election(self, key):
        if key in [ESC, CTRL_C]:
            raise CancelException

        if key == ENTER:
            return 0

        return key - ord('a')

    def is_valid_election(self, election):
        return election in [None] + range(0, self.index)

    def insert_path(self, path):
        if path in self.paths:
            return

        self.paths.append(path)
        self.index += 1
        if self.index > self.max_size:
            raise FullException

        suffix = ''
        if path == os.getcwd():
            suffix = ' (the current directory)'

        if self.index == 1:
            suffix += ' [ENTER]'

        rprint("{char:c}: {path}{suffix}\r\n".format(**dict(
                    char = self.index + ord('a') - 1,
                    path = highlight_pattern(config.pattern, path).replace(USERDIR, '~', 1),
                    suffix = suffix)))


class ProcessPoll(object):
    def __init__(self):
        self.task_queue = mp.JoinableQueue()
        self.output_queue = mp.Queue()

        self.workers = []
        for i in range(mp.cpu_count() - 1):
            worker = mp.Process(target=self.worker, args=(self.task_queue, self.output_queue))
            worker.start()
            self.workers.append(worker)

    def add_task(self, func, *args):
        self.task_queue.put((func, args))

    def has_tasks(self):
        return not self.task_queue._unfinished_tasks._semlock._is_zero()

    def terminate(self):
        for w in self.workers:
            self.task_queue.put('STOP')

        time.sleep(0.1)

        for w in self.workers:
            if w.is_alive():
#                print 'terminating', w
                w.terminate()
                w.join()

#        print 'all terminated'

    @staticmethod
    def worker(tasks, output):
        for func, args in iter(tasks.get, 'STOP'):
            # rprint("\n%s %s" % (func.__name__, args))
            func(output, *args)
            tasks.task_done()


class Go2:
    def __init__(self):
        self.poll = ProcessPoll()

    def main(self):
        self.cache = PathStore(GO2CACHE)
        self.history = PathStore(GO2HISTORY)

        self.create_tasks()
        ui = UI(self.poll)

        try:
            target = ui.run()
            rprint("Changing to: {0}\n".format(high(target)))
            save_target(target)
            self.history.insert_and_save(target)
            self.cache.insert_and_save(ui.paths)

        except CancelException:
            print("Canceled by user")
        except NotMatchException:
            print("Pattern does not match\r")

        self.poll.terminate()

    def history_not_related(self):
        history_paths = []
        for p in sorted(self.history.data, key=len):
            if any(p.startswith(x) for x in history_paths):
                continue
            history_paths.append(p)

        print str.join('\n', history_paths)

    def create_tasks(self):
        for pf in [self.cache, self.history]:
            self.poll.add_task(file_task, pf)

        paths = [os.getcwd(), USERDIR]
#        paths.extend(self.history.data)

        if config.from_root:
            paths.append('/')

        for path in paths:
            self.poll.add_task(tree_task, path)


def create_directory_wizard(path):
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
            os.mkdir(path)
        except OSError, e:
            print e
            sys.exit(1)

        print("go2: Making and changing to directory '%s'." % path)
        save_in_history(path)
        save_target(path)
        return 0

    # (s)earch
    Go2().main()


def chdir_decorator():
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

    if os.path.exists(target):
        save_in_history(target)
        save_target(target)
        return 0

    return create_directory_wizard(target)


def parse_args(args):
    parser = argparse.ArgumentParser(
        prog='go2',
        description='''go2 is a fast directory finder.
This is version {0}, Copyright (C) 2004-2011 David Villa Alises.
go2 comes with ABSOLUTELY NO WARRANTY; This is free software, and you
are welcome to redistribute it under certain conditions; See COPYING
for details.'''.format(VERSION),
        epilog='.',
        formatter_class=argparse.RawDescriptionHelpFormatter)

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
    retval.match_func = match_single if len(retval.pattern) == 1 else match_multi
    retval.apply_case = str.lower if retval.ignorecase else str

    if retval.ignorecase:
        retval.pattern = [x.lower() for x in retval.pattern]

    return retval


if __name__ == '__main__':
    if not os.path.exists(GO2DIR):
        os.mkdir(GO2DIR)

    config = parse_args(sys.argv[1:])
#    print config

    if config.setup:
        sys.exit(go2setup())

    if config.chdir:
        sys.exit(chdir_decorator())

    if not config.pattern:
        print("go2.py: error: too few arguments\n")
        config.parser.print_help()
        sys.exit(1)

    Go2().main()
