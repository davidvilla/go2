#! /usr/bin/python -u
# -*- coding: utf-8 -*-

# go2.py
#
# Copyright (C) 2004,2005,2006,2007 David Villa Alises
#
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


import os, sys, tty, termios, select, re
import thread, threading
import subprocess
import signal
import string
import time
import logging
import getopt
import itertools

os.environ['LANG'] = 'C'


ESC = 27
CTRL_C = 3
ENTER = 13

#FILES
USERDIR    = os.environ['HOME']
GO2DIR     = os.path.join(USERDIR, '.go2')
GO2INCLUDE = os.path.join(GO2DIR, 'include')
GO2EXCLUDE = os.path.join(GO2DIR, 'exclude')
GO2HISTORY = os.path.join(GO2DIR, 'history')
GO2CACHE   = os.path.join(GO2DIR, 'cache')
GO2CONFIG  = os.path.join(GO2DIR, 'config')
GO2TMP     = os.path.join(GO2DIR, 'tmp')
GO2LOG     = os.path.join(GO2DIR, 'log')
GO2GUI     = os.path.join(os.path.split(sys.argv[0])[0], 'go2.glade2')
#GO2GUI = os.environ['HOME'] + '/repos/go2/trunk/go2.glade2'


# states
WORKING, WAITING, CANCELED, \
NOTFOUND, FINISH,  FULL,    NOTEXIST, SKIP = range(8)


sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

class Singleton(type):
    def __init__(cls, *args):
        cls.__instance = None
    def __call__(cls, *args, **kargs):
        if not cls.__instance:
            cls.__instance = type.__call__(cls, *args, **kargs)
        return cls.__instance


class Observable:
    def __init__(self):
        self.__observers = []

    def attach(self, cb):
        self.__observers.append(cb)

    def detach(self, cb):
        self.__observers.remove(cb)

    def notify(self, val):
        for f in self.__observers:
            f(val)


def rprint(cad):
    print '\r' + cad,


#-- path checkers
def hidden(path):
    return (os.sep + '.') in path

def is_mine(path):
    return path.startswith(USERDIR)

#--

def filterout_hidden(pathlist):
    return [x for x in pathlist if not hidden(x)]

def match_single(path):
    path = Config().apply_case(path)

    #if Config().ignorecase:
    #    path = path.lower()

    return os.path.basename(path).startswith(Config().pattern[0])

def match_multi(path):
    path = Config().apply_case(path)

    #if Config().ignorecase:
    #    path = path.lower()

    pattern = Config().pattern
    items = path.split(os.sep)[1:]

    match = items[-1].startswith(pattern[-1])
    if not match: return False

    p = len(pattern) - 2
    for i in items[-2::-1]:
        if p < 0: return True
        if i.startswith(pattern[p]): p -= 1

    return False


def highlight(pattern, path, before, after, flags=0):
    items = path.split(os.sep)

    p = len(pattern) - 1
    for i in range(len(items)-1,-1,-1):
        if p < 0: break
        if Config().apply_case(items[i]).startswith(Config().apply_case(pattern[p])):
            orig = items[i][:len(pattern[p])]
            items[i] = items[i].replace(orig,
                                        before + orig + after, 1)
            p -= 1

    return os.sep.join(items)


# write selected dirname to file
def saveTarget(dirname):
    fd = open(GO2TMP, 'w')
    fd.write(dirname)
    fd.close()


class PathAsserts:
    "Delegate for path test functions"
    def __init__(self):
        self.filters = []

    def add(self, func):
        self.filters.append(func)

    def __call__(self, path):
        for f in self.filters:
            if f(path): return True

        return False



class ConsoleUI(threading.Thread):

    HIGH = chr(27)+'[1m'
    LOW = chr(27)+'[m'

    maxItem = 26

    def __init__(self, manager):
	threading.Thread.__init__(self, name='ConsoleUI')
        self.__mgr = manager
	self.__matches = 0
        self.__state = WORKING
        self.__last = 0
        self.__index = ord('a')
        self.__clean_prompt = len('Select a path:  ') * ' '
        self.log = logging.getLogger('ConsoleUI')

        if not Config().list_only:
            self.__mgr.state_attach(self)

        self.__mgr.path_attach(self)


    def __del__(self):
	pass #self.ttyrestore()

    def ttyrestore(self):
        tty.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)

    def run(self):
        if Config().list_only: return

        self.old_settings = tty.tcgetattr(sys.stdin)
        tty.setraw(sys.stdin)
        po = select.poll()
        po.register(sys.stdin, select.POLLIN)
        election = None

	while 1:
            if len(po.poll(100)) == 0:
                if self.__state == NOTFOUND:
                    break

                elif self.__state == WAITING and self.__matches == 1:
                    key = ENTER

                else:
                    continue
            else:
                key = ord(sys.stdin.read(1))

	    if key in [ESC, CTRL_C]:
		election = None
		break

            if key == ENTER:
                election = 0
            else:
                election = key - ord('a')

	    if election in range(0, self.__matches):
		break

        self.ttyrestore()
        self.__mgr.set_election(election)


    def state_update(self, state):
        self.__state = state

	rprint (self.__clean_prompt)

	if state == WAITING:
	    rprint('Select a path: ')
	elif state == CANCELED:
	    rprint('Canceled by user')
	elif state == NOTFOUND:
            self.log.info("Pattern doesn't match")
	    rprint("Pattern doesn't match\n\r")
	elif state == FULL:
            self.log.warning('Warning: Too many matches')
	    rprint('Warning: Too many matches!\n')
	elif state == FINISH:
	    rprint("Changing to: %s%s%s\n" % \
                    (self.HIGH, self.__mgr.dirname, self.LOW))
	elif state == WORKING:
            rprint('Searching...')
        elif state == SKIP:
            rprint("That's the current directory, nothing to be done\n")
	else:
	    rprint("Internal ERROR: unknown state '%d'\n" % state)


    def path_update(self, path):
        self.__matches += 1

        if self.__matches > self.maxItem:
            raise Manager.FullException

        assert self.__state == WORKING

        if Config().list_only:
            rprint("%s\n" % path)
            return

        msg = ''
        if path == os.getcwd():
            msg = ' (the current directory)'

        if self.__matches == 1:
            msg += ' [ENTER]'

        path = highlight(Config().pattern,
                         path, self.HIGH, self.LOW).\
                         replace(USERDIR, '~')

        rprint("%c: %s%s\n" % (chr(self.__index), path.ljust(16), msg))
        rprint('\rSearching...')
        self.__index += 1


class PathList(Observable):

    class AlreadyExistsException: pass
    def __init__(self):
        Observable.__init__(self)
        self.data = []
        self.delayed = []
        self.log = logging.getLogger('PathList')
        self.lock = threading.Lock()

    def append_delayed(self, item):
        if item not in self.delayed:
            self.delayed.append(item)

    def commit_delayed(self):
        for i in self.delayed:
            self.append(i)

    def append(self, item):
        if item in self.data:
            raise self.AlreadyExistsException

        self.log.debug("[%s]: %s" % (len(self), item))
        self.lock.acquire()
        self.data.append(item)
        self.notify(item)
        self.lock.release()

    def __getitem__(self, index):
        return self.data[index]

    def __len__(self):
        return len(self.data)



def loadlines(fname):
    if not os.path.exists(fname): return []

    fd = open(fname)
    lines = [i.strip() for i in fd.readlines()]
    fd.close()
    return [i for i in lines if i]


class PathFile:
    "Manage a file holding a path set"
    def __init__(self, filename, size = 100):
        self.filename = filename
        self.size = size
        self.log = logging.getLogger('PathFile [%s]' % os.path.split(filename)[-1])
        self.data = loadlines(filename)

        if not Config().process_hidden:
            self.data = filterout_hidden(self.data)

    def insert(self, item):
        self.log.debug("   Saving to file: %s (%s)" % (item,
                                                      str(len(self.data))))
        if item in self.data: self.data.remove(item)
        self.data.insert(0, item)

    def commit(self):
        fd = open(self.filename, 'w')
        fd.write(string.join(self.data[:self.size],'\n') + '\n')
        fd.close()


class Worker(threading.Thread):

    def __init__(self, manager, root, exclude):
        threading.Thread.__init__(self, name = self.__class__.__name__)
        self.mgr = manager
        self.root = root
        self.__exclude = exclude # lista de rutas excluidas
        self.count = 0

    def is_excluded(self, path):
        # Comprueba que la ruta absoluta 'path' no está excluida
        # FIXME: Comprobar también que el nombre de directorio no está
        # excluido (ej .svn), es decir, rutas relativas
        for p in self.__exclude:
            if path.startswith(p): return True
        return False


class LocateWorker(Worker):
    "Parse locate output"
    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)
        self.log = logging.getLogger('Locate')
        self.log.debug("[New]")

    def run(self):
        options = '-l 1000 -e -b '
        if Config().ignorecase:
            options += '-i '
        cmd = 'locate %s %s' % (options, Config().pattern[0])
        self.log.debug('locate cmd: %s' % cmd)

        locate = subprocess.Popen(cmd, shell=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  close_fds=True)

        exclude = PathAsserts()
        exclude.add(lambda x: not os.path.isdir(x))
        if not Config().process_hidden: exclude.add(hidden)
        if not Config().from_root:      exclude.add(lambda x: not is_mine(x))
        exclude.add(self.is_excluded)
        exclude.add(lambda x: not Config().match_func(x))

        for i in locate.stdout:
            if self.mgr.stop.isSet():
                os.kill(locate.pid, signal.SIGKILL)
                return

            i = i.strip('\n')
            self.log.debug(i)

            if not exclude(i):
                self.mgr.path_notify(i)



class HistoryWorker(Worker):
    "Search in directories selected at any time"

    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)
        self.fname = kargs['fname']
        self.drop = []
        self.pFile = PathFile(self.fname, 500)
        self.log = logging.getLogger('History')
        self.log.debug("[len:%s]" % len(self.pFile.data))


    def run(self):
        for i in self.pFile.data:
            if self.mgr.stop.isSet(): return

            self.log.debug (i)
            if Config().match_func(i):
                if not os.path.exists(i):
                    self.drop.append(i)
                    continue

                if self.is_excluded(i): continue

                self.mgr.path_notify(i)

            self.mgr.add_work(i) # search in all historic paths


    def state_update(self, state):
        if state != FINISH: return
        for i in self.drop:
            self.pFile.data.remove(i)
        self.pFile.insert(self.mgr.dirname)
        self.pFile.commit()


# save all directories that appears in any seach
class CacheWorker(Worker):

    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)
        self.fname = kargs['fname']
        self.drop = []
        self.pFile = PathFile(self.fname, 1000)
        self.log = logging.getLogger('Cache')
        self.log.debug("[New, len:%s]" % len(self.pFile.data))

    def run(self):
        for i in self.pFile.data:
            if self.mgr.stop.isSet(): return

            if Config().match_func(i):
                if not os.path.exists(i):
                    self.drop.append(i)
                    continue

                if self.is_excluded(i): continue

                self.mgr.path_notify(i)


    def path_update(self, path):
        self.pFile.insert(path)

    def state_update(self, state):
        if state in (FINISH, CANCELED):
            for i in self.drop: self.pFile.data.remove(i)
            if self.mgr.dirname in self.pFile.data:
                self.pFile.data.remove(self.mgr.dirname)
            self.pFile.commit()


class FindWorker(Worker):
    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)
        self.log = logging.getLogger('Locate')
        self.log.debug("[%s] New FindWorker for '%s'" % (id(self), self.root))

    def run(self):
        name = '-name'
        if Config().ignorecase:
            name = '-iname '
        cmd = 'find %s -type d %s "%s*"' % (self.root, name, Config().pattern[-1])
        # FIXME: puede que find no exista
        self.ps = subprocess.Popen(cmd, shell=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                close_fds=True)

        logging.info('find cmd[%s]: %s' % (self.ps.pid, cmd))

        exclude = PathAsserts()
        exclude.add(lambda x: not os.path.isdir(x))
        if not Config().process_hidden: exclude.add(hidden)
        if not Config().from_root:      exclude.add(lambda x: not is_mine(x))
        exclude.add(self.is_excluded)
        exclude.add(lambda x: not Config().match_func(x))

        for i in self.ps.stdout:
            if self.mgr.stop.isSet():
                self.log.debug('Killing find %s' % self.ps.pid)
                os.kill(self.ps.pid, signal.SIGKILL)
                break

            i = i.strip('\n')
            self.log.debug(i)

            if exclude(i): continue
            self.mgr.path_notify(i)

        self.mgr.state_detach(self)


    def state_update(self, state):
        if state in [CANCELED, FINISH]:
            self.log.debug('Killing find %s at update()' % self.ps.pid)
            try:
                os.kill(self.ps.pid, signal.SIGKILL)
            except OSError, e:
                rprint('\n %s %s \n' % (e, self.ps.pid))


class DiskWorker(Worker):

    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)
        self.log = logging.getLogger('Disk')
        self.log.debug("[New (%s) for '%s']" % (id(self), self.root))


    def run(self):

        def walkerror(e):
            self.log.warning(e)

        exclude = PathAsserts()
        if not Config().process_hidden: exclude.add(hidden)
        exclude.add(self.is_excluded)

        for root, dirs, files in os.walk(self.root, onerror=walkerror):
            if self.mgr.stop.isSet(): return

            if len(dirs) == 0: continue

            for d in list(dirs):
                path = os.path.join(root, d)

                if exclude(path):
                    dirs.remove(d)
                    continue

#                if not Config().from_root and os.path.islink(path):
#                    realpath = os.path.abspath(os.path.join(os.path.dirname(path), os.readlink(path)))
#                    #rprint("LINK: '%s' -> '%s'\n" % (path, realpath))
#                    self.log.info("LINK: '%s' -> '%s'" % (path, realpath))
#                    self.mgr.add_work(realpath)
#                    dirs.remove(d)
#                    continue

                if os.path.islink(path): continue

                if Config().match_func(path):
                    self.mgr.path_notify(path)
                    self.count += 1

                elif Config().pattern > 1 and match_single(path):
                    self.mgr.add_work(path)
                    dirs.remove(d)



class ParentWorker(Worker):
    "Search in ancestor directories"
    def run(self):
        lis =  os.getcwd().split(os.sep)
        for i in range(len(lis)-1, 0, -1):
            path = string.join(lis[:i] + [''], os.sep)
            self.mgr.path_notify(path)


class Manager(object):

    class FullException: pass

    def __init__(self):
        self.path_list = PathList()
        self.optionalList = PathList()
        self.__state_observers = []
        self.__path_observers = []
        self.exclude = Config().exclude[:]

        self.pending_lock = threading.Lock()
        self.pending = []

        if Config().parent_mode:
            self.main_job = self.parent_job
        elif Config().history_mode:
            self.main_job = self.history_job

        self.workers = []
        self.stop = threading.Event()
        self.state = WORKING

        self.tinit = time.time()
        self.dirname = None


    def create_worker(self, workerClass, root = None, **kargs):
        if self.stop.isSet(): return None

        if root in self.exclude:
            logging.info("create_worker: '%s' previously exluded" % root)
            return None

        if root:
            exclude_cp = [x for x in Config().exclude if not root.startswith(x)]
            self.exclude.append(root)
        else:
            exclude_cp = Config().exclude[:]

        w = workerClass(self, root, exclude_cp, **kargs)
        self.workers.append(w)

        if hasattr(w, 'state_update'):
            self.state_attach(w)
        if hasattr(w, 'path_update'):
            self.path_attach(w)

        w.start()
        return w

    def parent_job(self):
        self.create_worker(ParentWorker)

    def history_job(self):
        logging.info('go2: history mode')
        self.create_worker(HistoryWorker, fname = GO2HISTORY)

    def main_job(self):
        if Config().match_func(os.getcwd()):
            self.path_notify(os.getcwd())

        #if pattern is a current subdirectory name
        if len(Config().pattern) == 1 and os.path.isdir(Config().pattern[0]):
            self.path_notify(os.path.abspath(Config().pattern[0]))

        w = self.create_worker(HistoryWorker, fname = GO2HISTORY)
        if w: w.join(1)

        w = self.create_worker(CacheWorker, fname = GO2CACHE)
        if w: w.join(1)

        self.pending.extend(list(set([os.getcwd(), USERDIR])))

        if Config().from_root:
            self.pending.append('/')
            return

        self.pending.extend(Config().include)


    def wait_jobs_end(self):
        #ocate_run = False
        locate_run = True  # never run locate
        while 1:
            if self.pending:
                logging.debug('PENDIND: %s' % self.pending)
            if self.pending and threading.activeCount() < 20:
                path = self.pending[0]
                self.pending_lock.acquire()
                self.pending = self.pending[1:]
                self.pending_lock.release()

                self.create_worker(DiskWorker, path)
                #manager.createWorker(FindWorker, path)

            if self.stop.isSet() or \
                   not (self.__any_worker_alive() or self.pending):
                break

            select.select([],[],[], 0.25)  # espera pasiva
            if not locate_run and time.time() - self.tinit > 5:
                locate_run = True
                if Config().locate:
                    w = self.create_worker(LocateWorker)


	if self.stop.isSet(): return

        self.path_list.commit_delayed()

        if len(self.path_list) == 0:
            self.state_notify(NOTFOUND)
            return

        self.state_notify(WAITING)

        for w in self.workers:
            logging.debug("worker %s (%s) found %s" % \
                          (id(w), w.__class__.__name__.ljust(13), w.count))

    def run(self):
        self.main_job()
        self.wait_jobs_end()
        while(self.__any_worker_alive()):
            select.select([],[],[], 0.5)


    def add_work(self, path):
        if path in self.pending or path in self.exclude: return

        self.pending_lock.acquire()
        self.pending.append(path)
        self.pending_lock.release()


    def state_attach(self, ob):
        self.__state_observers.append(ob)

    def state_detach(self, ob):
        self.__state_observers.remove(ob)

    def path_attach(self, ob):
        self.path_list.attach(ob.path_update)

    def state_notify(self, state):
        self.state = state

        for o in self.__state_observers:
            o.state_update(self.state)

        if state == FULL:
            self.state_notify(WAITING)
            self.stop.set()

    def path_notify(self, path):
        if self.state != WORKING: return

        try:
            self.path_list.append(path)
        except PathList.AlreadyExistsException:
            return
        except self.FullException:
            self.state_notify(FULL)


    def __any_worker_alive(self):
        #Change to "any()" when Debian uses python2.5
        for i in self.workers:
            if i.isAlive(): return True
        return False


    def set_election(self, election):
        if self.state == NOTFOUND: return
        self.stop.set()
        if election == None:
            self.state_notify(CANCELED)
            return

        self.dirname = self.path_list[election]

        if self.dirname == os.getcwd():
            self.state_notify(SKIP)
            return

        if not os.path.exists(self.dirname):
            self.state_notify(NOTEXIST)
            return

        self.state_notify(FINISH)

        if Config().cmd:
            cmd = Config().cmd
            cmdlist = cmd.split()

            for i in range(len(cmdlist)):
                if '%d' in cmdlist[i]:
                    aux = cmdlist[i].replace('%d', '%s')
                    cmdlist[i] = aux % self.dirname

            logging.info("command is: '%s'" % cmdlist)
            os.chdir(self.dirname)
            os.execvp(cmdlist[0], cmdlist)
        else:
            saveTarget(self.dirname)


def leaveAdvice(*args):
    print '\n\nWarning: Ctrl-C ignored, to abort press ESC.'

def break_handler(*args):
    print args

def go2setup():
    if os.system('grep go2.sh ~/.bashrc > /dev/null') == 0:
        print('go2 already configured, skipping.')
        return 1

    os.system('echo "\n[ -e /usr/lib/go2/go2.sh ] && source /usr/lib/go2/go2.sh\nalias cd=\'go2 --cd\'" >> ~/.bashrc')

    print('Setting up go2. It will be ready in next shell session.')
    return 0


def usage():
    prgname = os.path.splitext(os.path.basename(sys.argv[0]))[0]
    date = '$Date$'
    version = '0.'+date[9:17].replace('-','')
    print 'go2 is a fast directory finder.'
    print '''This is version %s, Copyright (C) 2007 David Villa Alises
go2 comes with ABSOLUTELY NO WARRANTY; This is free software, and you are
welcome to redistribute it under certain conditions; See COPYING for details.
''' % (version)

    print 'Usage: %s [options] <pattern>' % prgname
    print """
options:
  -i           ignore case                       (default: case sensitive)
  -r           search in whole file system       (default: $HOME only)
  -d           search into hidden directories    (default: skip hidden)
  -H           list history
  -l           list only, print matches and exit
  --gui        GUI mode
  --cmd <cmd>  exec 'cmd'                        (default: chdir)
  --dir <dir>  search from 'dir' directory       (default: current)
"""
    return 1



################################

class Config(object):

    __metaclass__ = Singleton

    class EmptyPatternException: pass
    class NoValidPatternException: pass

    def __init__(self, argv=[]):
        self.history_mode = False
        self.parent_mode = False
        self.from_root = False
        self.ignorecase = False
        self.process_hidden = False
        self.locate = True
        self.list_only = False
        self.match_func = match_single
        self.pattern = None
        self.exclude = []
        self.include = []
        self.cmd = None

        self.apply_case = lambda x:x

        if not os.path.exists(GO2DIR):
            os.mkdir(GO2DIR)

        # load file specified excluded paths
        self.exclude = loadlines(GO2EXCLUDE)
        if self.exclude: logging.debug('exclude: %s' % self.exclude)

        self.include = loadlines(GO2INCLUDE)
        if self.include: logging.debug('include: %s' % self.include)



        try:
            opts, self.pattern = getopt.getopt(argv[1:], 'Hirdl',
                                               ['setup','no-locate', 'log',
                                                'debug', 'gui',
                                                'cmd=', 'dir='])
        except getopt.GetoptError:
            sys.exit(usage())

        for o, a in opts:
            if o == '-i':
                self.ignorecase = True
                self.apply_case = string.lower
            if o == '-l':
                self.list_only = True
            if o == '-r':
                self.from_root = True
            if o == '-d':
                self.process_hidden = True
            if o == '-H':
                self.history_mode = True
                self.pattern = ['']    # hack para que todos hagan matching
                return
            if o == '--no-locate':
                self.locate = False
            if o == '--setup':
                sys.exit(go2setup())
            if o == '--cmd':
                self.cmd = a
            if o == '--dir':
                if os.path.isdir(a): dirname = a
                elif os.path.isfile(a):
                    dirname = os.path.split(a)[0]
                else: continue
                logging.debug('dir:  ' + dirname)
                os.chdir(dirname)

    def parse_pattern(self):
        if not self.pattern:
            raise self.EmptyPatternException

        if self.pattern[0] == '.':
            p = PathFile(GO2HISTORY)
            p.insert(os.getcwd())
            p.commit()
            sys.exit(0)

        if self.pattern[0] == '..':
            self.parent_mode = True
            self.pattern = ['']

        if self.ignorecase:
            self.pattern = [x.lower() for x in self.pattern]

        if len(self.pattern) > 1:
            self.match_func = match_multi



class GtkFrontend:
    def __init__(self, argv):
        self.argv = argv
        cfg = Config(argv)

        self.glade = gtk.glade.XML(GO2GUI)
        self.glade.signal_autoconnect(self)

        # load cmdline config
        if cfg.pattern:
            self.wg_entry.set_text(' '.join(cfg.pattern))

        cmds = ['gnome-terminal', 'nautilus %d', 'cd']
        combo_model = self.wg_combo_cmd.get_model()
        for c in cmds:
            combo_model.append([c])

        if cfg.cmd:
            self.wg_combo_cmd.child.set_text(cfg.cmd)
        else:
            self.wg_combo_cmd.child.set_text(combo_model[0][0])

        # setup treeview
        self.store = gtk.ListStore(str, int)
        self.wg_treeview.set_model(self.store)

        self.tvcolumn = gtk.TreeViewColumn('Path', gtk.CellRendererText(),
                                           markup=0)
        self.tvcolumn.set_sort_column_id(0)

        self.wg_treeview.append_column(self.tvcolumn)
        self.selection = self.wg_treeview.get_selection()
        self.selection.set_mode(gtk.SELECTION_SINGLE)

        self.__n = 0
        self.source_id = None


    def __getattr__(self, name):
        "get widget if attribute starts with 'wg_'"
        if not name.startswith('wg_'):
            raise AttributeError("'%s' isn't a widget" % name)

        widget = self.glade.get_widget(name[3:])
        if widget == None:
            raise AttributeError("Widget '%s' not found" % name)

        self.__dict__[name] = widget
        return widget


    def update_config(self):
        cfg = Config()
        cfg.pattern = self.wg_entry.get_text().split()
        cfg.parse_pattern()

        # switches
        cfg.from_root = self.wg_checkbutton_root.get_active()
        cfg.ignorecase = self.wg_checkbutton_case.get_active()

        cfg.process_hidden = not self.wg_checkbutton_hidden.get_active()

        cfg.cmd = self.wg_combo_cmd.child.get_text().strip()
        if cfg.cmd == 'chdir':
            cfg.cmd = None

    def main(self):
        gtk.main()

    def work(self):
        try:
            self.update_config()
        except Config.EmptyPatternException:
            logging.debug('Falta diálogo de error, vacio')
            gobject.idle_add(self.gui_reset)
            return
        except Config.NoValidPatternException:
            logging.debug('Falta diálogo de error, no válido')
            return

        try:
            gobject.idle_add(self.gui_working)
            self.manager = Manager()
            self.manager.path_attach(self)
            self.manager.state_attach(self)
            self.manager.run()
        except AttributeError, e:
            print e


    def gui_reset(self, entry='', progress=''):
        if entry != None:
            self.wg_entry.set_text(entry)
        self.wg_entry.grab_focus()
        self.wg_button_search.set_sensitive(True)
        self.store.clear()
        self.wg_button_cancel.set_sensitive(False)
        self.wg_button_clean.set_sensitive(False)
        self.wg_button_go.set_sensitive(False)
        self.progressbar_text(progress)

    def gui_working(self):
        def pulse():
            self.wg_progressbar.pulse()
            return True

        self.wg_button_search.set_sensitive(False)
        self.wg_button_cancel.set_sensitive(True)
        self.wg_button_clean.set_sensitive(False)
        self.wg_button_go.set_sensitive(False)
        self.source_id = gobject.timeout_add(150, pulse)

    def progressbar_text(self, text):
        gobject.source_remove(self.source_id)
        self.wg_progressbar.set_fraction(0)
        self.wg_progressbar.set_text(text)

    def on_window_delete_event(self, *args):
        gtk.main_quit()

    def on_button_search_clicked(self, wd):
        self.store.clear()
        self.__n = 0
        thread.start_new_thread(self.work, ())

    def on_button_cancel_clicked(self, wd):
        self.manager.set_election(None)
        self.gui_reset()

    def on_button_clean_clicked(self, wd):
        self.gui_reset()

    def on_button_go_clicked(self, wd):
        self.update_config()
        model, it = self.selection.get_selected()
        if it == None: return # no hay selección
        self.manager.set_election(model[it][1])
        gtk.main_quit()

    def offline_path_update(self, path):
        tagged_path = highlight(Config().pattern, path, '<b>', '</b>').\
                      replace(USERDIR, '~')

        self.store.append([tagged_path, self.__n])

        if self.__n == 0:
            self.wg_button_go.set_sensitive(True)
            self.wg_treeview.grab_focus()

        self.__n += 1
        return False

    def path_update(self, path):
        gobject.idle_add(self.offline_path_update, path)

    def offline_state_update(self, state):
        if state == NOTFOUND:
            logging.debug('NOTFOUND')
            self.gui_reset(None, 'Not Found')

        if state == WAITING:
            logging.debug('WAITING')
            self.wg_button_search.set_sensitive(True)
            self.wg_button_cancel.set_sensitive(False)
            self.wg_button_clean.set_sensitive(True)
            self.progressbar_text('Ready: %d matches' % len(self.manager.path_list))

        if state == CANCELED:
            pass

        return False

    def state_update(self, state):
        gobject.idle_add(self.offline_state_update, state)



def console_main(argv):
    try:
        config = Config(argv)
        config.parse_pattern()
    except Config.EmptyPatternException:
        sys.exit(usage())
    except Config.NoValidPatternException:
        print 'go2: invalid pattern', args
        sys.exit(1)


    #signal.signal(signal.SIGQUIT, leaveAdvice)
    signal.signal(signal.SIGINT, leaveAdvice)
    #signal.signal(signal.SIGTERM, leaveAdvice)

    manager = Manager()
    console = ConsoleUI(manager)

    console.start()
    manager.run()
    console.join()


class Dummy(): pass

if __name__ == '__main__':

    try:
        os.getcwd()
    except OSError,e:
        logging.error("Current directory does not exists!")
        saveTarget(USERDIR)
        sys.exit(1)

    argv = sys.argv[:]
    if os.path.exists(GO2CONFIG):
        argv[1:1]  = file(GO2CONFIG).read().split()

    if len(argv) > 1 and '--cd' == argv[1]:
        if len(argv) == 2:
            saveTarget(USERDIR)
            sys.exit(0)

        params = ' '.join(argv[2:])
        try:
            target = os.path.abspath(params)
        except OSError, e:
            logging.error(e)
            saveTarget(USERDIR)
            sys.exit(0)

        if not os.path.exists(target):
            saveTarget(params)
            sys.exit(1)

        hist = PathFile(GO2HISTORY, 1000)
        hist.insert(target)
        hist.commit()
        saveTarget(target)
        sys.exit(0)


    if '--log' in argv or '--debug' in argv:
        logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s %(levelname)-8s %(name)-10s %(message)s',
                        filename=GO2LOG)

    if '--debug' in argv:
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG)
        formatter = logging.Formatter('\r%(levelname)-8s %(message)s')
        console.setFormatter(formatter)
        logging.getLogger().addHandler(console)

    else:
        logging.getLogger().setLevel(logging.CRITICAL)


    logging.info("\n\n---------- [go2 '%s']" % sys.argv[1:])

    #try:
    #    import psyco
    #    psyco.full()
    #except ImportError:
    #    logging.warning("psyco not available")

    has_DISPLAY = os.environ.has_key("DISPLAY")
    if not has_DISPLAY:
        logging.warning("$DISPLAY isn't set, fallback console mode")

    if "--gui" in argv and has_DISPLAY:
        import gobject
        import gtk, gtk.glade
        gobject.threads_init()
        GtkFrontend(argv).main()
    else:
        console_main(argv)
