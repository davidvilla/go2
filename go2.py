#! /usr/bin/python2.4 -u
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
import subprocess

os.environ['LANG'] = 'C'


ESC = 27
ENTER = 13

#FILES
GO2DIR =     os.path.join(os.environ['HOME'], '.go2')
GO2EXCLUDE = os.path.join(GO2DIR, 'exclude')
GO2HISTORY = os.path.join(GO2DIR, 'history')
GO2CACHE =   os.path.join(GO2DIR, 'cache')
GO2CONFIG =  os.path.join(GO2DIR, 'config') 
GO2TMP =     os.path.join(GO2DIR, 'tmp')
GO2LOG =     os.path.join(GO2DIR, 'log')
GO2GUI = os.path.join(os.path.split(sys.argv[0])[0], 'go2.glade2')
GO2GUI = '/home/david/repos/go2/trunk/go2.glade2'

# states
INITIAL,  WORKING, WAITING, CANCELED, \
NOTFOUND, FINISH,  FULL,    NOTEXIST = range(8)


sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

class Singleton(type):
    def __init__(cls, *args):
        cls.__instance = None
    def __call__(cls, *args, **kargs):
        if not cls.__instance:
            cls.__instance = type.__call__(cls, *args, **kargs)
        return cls.__instance


#-- path checkers
def hidden(path):
    return (os.sep + '.') in path

def not_mine(path):
    return not path.startswith(os.environ['HOME'])

#--



def filterout_hidden(pathlist):
    return [x for x in pathlist if not hidden(x)]

def match_single(path):
    if Config().ignorecase:
        path = path.lower()

    retval = os.path.basename(path).startswith(Config().pattern[0])
    #if retval:
    #    print os.path.basename(path)
    #    print Config().pattern[0]
    return retval


def match_single_re(path):
    return re.match(Config().re_pattern[0],
                    os.path.basename(path),
                    Config().flags)

def match_multi(path):
    if Config().ignorecase:
        path = path.lower()
    
    items = path.split(os.sep)[1:]
    pattern = Config().pattern

    match = items[-1].startswith(pattern[-1])
    if not match: return False

    p = len(pattern) -2
    for i in items[-2::-1]:
        if p < 0: return True
        if i.startswith(pattern[p]): p -= 1

    return False


def match_multi_re(path):
    "path must be a abspath"

    cfg = Config()
    items = path.split(os.sep)[1:]
    pattern = cfg.re_pattern

    match = re.match(pattern[-1], items[-1], cfg.flags)
    if not match: return False

    p = len(pattern) - 2
    for i in items[-2::-1]:
        if p < 0: return True
        if re.match(pattern[p], i, cfg.flags): p -= 1

    return False



def highlight(pattern, path, before, after, flags=0):
    #print '\rpattern:', pattern
    #print '\rpath:', path
    
    items = path.split(os.sep)
    #items = [re.escape(x) for x in path.split(os.sep)]
    #print items

#    pattern = [re.escape(x) for x in pattern]
    p = len(pattern) - 1
    for i in range(len(items)-1,-1,-1):
        if p < 0: break
        if items[i].startswith(pattern[p]):
        #if re.match(pattern[p], items[i], flags):
            orig = items[i][:len(pattern[p])]
            #print 'orig:', repr(orig)
            items[i] = items[i].replace(orig,
                                        before + orig + after, 1)
            p -= 1
            
    retval = os.sep.join(items)
    #print repr(retval)
    return retval


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

    def test(self, path):
        for f in self.filters:
            if f(path): return True

        return False

    def __call__(self, path):
        return self.test(path)
        

class ConsoleUI(threading.Thread):

    HIGH = chr(27)+'[1m'
    LOW = chr(27)+'[m'

    maxItem = 26
    
    def __init__(self):
	threading.Thread.__init__(self, name='ConsoleUI')
	self.__matches = 0
        self.state = None
        self.__last = 0
        self.__index = ord('a')
        manager.state_attach(self)
        manager.path_attach(self)

    def __del__(self):
	pass #self.ttyrestore()

    def ttyrestore(self):
        tty.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)

    def run(self):
        self.old_settings = tty.tcgetattr(sys.stdin)
        tty.setraw(sys.stdin)
        po = select.poll()
        po.register(sys.stdin, select.POLLIN)
        election = None
       
	while 1:
            if len(po.poll(250)) == 0:
                if self.state == NOTFOUND:
                    break
                
                elif self.state == WAITING and self.__matches == 1:
                    key = ENTER

                else:                
                    continue
            else:
                key = ord(sys.stdin.read(1))

	    if key == ESC:
		election = None
		break

            if key == ENTER:
                election = 0
            else:
                election = key - ord('a')
			
	    if election in range(0, self.__matches):
		break

        self.ttyrestore()
        manager.setElection(election)

    def state_update(self, state):
        self.state = state

        msg_select = '\rSelect a path: '
	print ('\r' + ' '*len(msg_select)),
		
	if state == WAITING:
	    print '\rSelect a path: ',
	elif state == CANCELED:
	    print '\rCanceled by user'
	elif state == NOTFOUND:
            logging.info("Pattern doesn't match")
	    print "\rPattern doesn't match\r"
	elif state == FULL:
            logging.warning('Warning: Too many matches')
	    print '\rWarning: Too many matches!'
	elif state == FINISH:
	    print "\rChanging to: %s%s%s" % \
                    (self.HIGH, manager.dirname, self.LOW)
	elif state == WORKING:
            print '\rSearching...',
            return
#	    newSize = len(manager.pathList)
#            for path in manager.pathList[self.__last:newSize]:
#                
#                # usar string.replace en lugar de re.sub??
#		path = re.sub('^' + os.environ['HOME'], '~',
#                              self.highlight(path))
#                
#		print "\r%c: %s" % (chr(self.__index),
#                                    path)
#                self.__index += 1
#
#            print '\rSearching...',
#            self.__last = newSize
	else:
	    print "\rInternal ERROR: unknown state '%d'\n" % state

    def path_update(self, path):
        self.__matches += 1

        if self.__matches > self.maxItem:
            raise Manager.FullException

        assert manager.state == WORKING

        path = re.sub('^' + os.environ['HOME'], '~',
                      highlight(Config().pattern,
                                path, self.HIGH, self.LOW, Config().flags))
                
        print "\r%c: %s" % (chr(self.__index), path.ljust(16))
        print '\rSearching...',       
        self.__index += 1


class PathList:

    class AlreadyExistsException: pass
    def __init__(self):
        self.data = []
        self.lock = threading.Lock()

    def append(self, item):
        if item in self.data:
            raise self.AlreadyExistsException

        logging.debug("PathList[%s]: %s" % (len(self), item))
        self.lock.acquire()
        self.data.append(item)
        self.lock.release()

    def __getitem__(self, index):
        return self.data[index]

    def __len__(self):
        return len(self.data)


class PathFile:
    "Manage a file which content a path set"
    def __init__(self, filename, size = 100):
        self.data = []
        self.filename = filename
        self.size = size
        if os.path.exists(filename): 
            fd = open(filename)
            self.data = [x.strip('\n') for x in fd.readlines()]
            fd.close()

        if not Config().process_hidden:
            self.data = filterout_hidden(self.data)

    def insert(self, item):
        logging.debug("Saving to file: %s (%s)" % (item, str(len(self.data))))
        if item in self.data: self.data.remove(item)
        self.data = [item] + self.data

    def commit(self):
        fd = open(self.filename, 'w')
        fd.write(string.join(self.data[:self.size],'\n') + '\n')
        fd.close()


class Worker(threading.Thread):
#    i = 0 #debería ser un atributo de clase

    def __init__(self, root, exclude):
        threading.Thread.__init__(self) #, name = "Worker %d" % self.i)
#        self.i += 1
        self.root = root
        self.__exclude = exclude
        self.count = 0

    def is_excluded(self, path):
        # Comprueba que la ruta absoluta 'path' no está excluida
        # FIXME: Comprobar también que el nombre de directorio no está
        # excluido (ej.svn), es decir, rutas relativas
        for p in self.__exclude:
            if path.startswith(p): return True
        return False

class LocateWorker(Worker):
    "Parse locate output"
    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)
        logging.info("New LocateWorker")
        
    def run(self):
        options = '-l 1000 -e -b '
        if Config().flags | re.IGNORECASE:
            options += '-i '
        cmd = 'locate %s %s' % (options, Config().pattern[0])
        logging.info('locate cmd: %s' % cmd)

        # FIXME: puede que locate no exista
        locate = subprocess.Popen(cmd, shell=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  close_fds=True)

        exclude = PathAsserts()
        exclude.add(lambda x: not os.path.isdir(x))
        if not Config().process_hidden: exclude.add(hidden)
        if not Config().from_root:      exclude.add(not_mine)
        exclude.add(self.is_excluded)
        exclude.add(lambda x: not Config().match_func(x))

        for i in locate.stdout:
            if manager.stop.isSet():
                os.kill(locate.pid, signal.SIGKILL)
                return

            i = i.strip('\n')
            logging.debug("locate-> '%s'" % i)
            
            if exclude(i): continue
            if Config().match_func(i):
                manager.path_notify(i)



class HistoryWorker(Worker):
    "Search in directories selected some time"

    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)
        logging.info("New HistoryWorker")        
        self.fname = kargs['fname']
        self.drop = []

    def run(self):
        self.pFile = PathFile(self.fname, 500)
        for i in self.pFile.data:
            if manager.stop.isSet(): return

            logging.debug ("History -> '%s'" % i)
            if Config().match_func(i):
                if not os.path.exists(i):
                    self.drop.append(i)
                    continue

                if self.is_excluded(i): continue

                manager.path_notify(i)

    def state_update(self, state):
        if state != FINISH: return
        for i in self.drop:
            self.pFile.data.remove(i)
        self.pFile.insert(manager.dirname)
        self.pFile.commit()


class CacheWorker(Worker):

    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)
        logging.info("New CacheWorker")
        self.fname = kargs['fname']
        self.drop = []

    def run(self):
        self.pFile = PathFile(self.fname, 1000)
        logging.info('cache len:' + str(len(self.pFile.data)))

        for i in self.pFile.data:
            if manager.stop.isSet(): return

            if Config().match_func(i):
                if not os.path.exists(i):
                    self.drop.append(i)
                    continue

                if self.is_excluded(i): continue

                manager.path_notify(i)

    def path_update(self, path):
        self.pFile.insert(path)
	
    def state_update(self, state):
        if state == FINISH:
            for i in self.drop: self.pFile.data.remove(i)
            self.pFile.commit()


class DiskWorker(Worker):

    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)
        logging.info("[%s] New DiskWorker for '%s'" % (id(self), self.root))

    def run(self):

        exclude = PathAsserts()
        if not Config().process_hidden: exclude.add(hidden)
        exclude.add(self.is_excluded)
        
        for root, dirs, files in os.walk(self.root):
            if manager.stop.isSet(): return

            if len(dirs) == 0: continue

            for d in list(dirs):
                #print d
                path = os.path.join(root, d)
                #if (d[0] == '.' and not opt.process_hidden) or \
                #    d in self.exclude or path in self.exclude:
                if exclude(path):
                    dirs.remove(d)
                    continue

                #print '\r\n', os.path.basename(path), path,
                #if os.path.basename(path) == "repos":
                #    print 'SINGLE', path

                if Config().match_func(path):
                    manager.path_notify(path)
                    self.count += 1
                elif Config().match_func == match_multi and match_single(path):
                    manager.createWorker(DiskWorker, path)
                    dirs.remove(d)


class ParentWorker(Worker):
    "Search in ancestor directories"
    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)

    def run(self):
        lis =  os.getcwd().split(os.sep)
        for i in range(len(lis)-1, 0, -1):
            path = string.join(lis[:i] + [''], os.sep)
            manager.path_notify(path)


class Manager(object):

    class FullException: pass

    def __init__(self):
        self.pathList = PathList()
        self.__observers = []
        self.__state_observers = []
        self.__path_observers = []
        self.cfg = Config()
        
        if self.cfg.parent_mode:
            self.mainJob = self.parentMode_job
        elif self.cfg.history_mode:
            self.mainJob = self.historyMode_job

        self.workers = []
        self.stop = threading.Event()
        self.state = INITIAL

        self.tinit = time.time()

    def createWorker(self, workerClass, root = None, **kargs):
        if self.stop.isSet(): return None

        if root:
            exclude_cp = [x for x in self.cfg.exclude if not root.startswith(x)]
            self.cfg.exclude.append(root)
        else:
            exclude_cp = self.cfg.exclude[:]

        w = workerClass(root, exclude_cp, **kargs)
        self.workers.append(w)

        if hasattr(w, 'state_update'):
            self.state_attach(w)
        if hasattr(w, 'path_update'):
            self.path_attach(w)
        
        w.start()
        return w

    def parentMode_job(self):
        self.state_notify(WORKING)
        self.createWorker(ParentWorker)

    def historyMode_job(self):
        logging.info('go2: history mode')
        self.state_notify(WORKING)
        self.createWorker(HistoryWorker, fname = GO2HISTORY)


    def mainJob2(self):
        self.state_notify(WORKING)
        
        dirs = list(set([os.getcwd()]))
        for target in dirs:
            self.createWorker(DiskWorker, target)


    def mainJob(self):
        self.state_notify(WORKING)
        
        w = self.createWorker(HistoryWorker, fname = GO2HISTORY)
        if w: w.join(1)

        # si el patrón es el nombre de un subdirectorio de pwd
        if len(self.cfg.pattern) == 1 and os.path.isdir(self.cfg.pattern[0]):
            self.path_notify(os.path.abspath(self.cfg.pattern[0]))

        w = self.createWorker(CacheWorker, fname = GO2CACHE)
        if w: w.join(1)
        
        dirs = list(set([os.getcwd(), os.environ['HOME']]))
        #dirs = list(set([os.getcwd()]))

        if self.cfg.from_root:
            dirs.append('/')

        for target in dirs:
            self.createWorker(DiskWorker, target)


    def waitJobsEnd(self):
        locate_run = False
        while 1:
            if self.stop.isSet() or not self.any_worker_alive():
                break
            
            select.select([],[],[], 0.25)  # espera pasiva
            if time.time() - self.tinit > 5 and not locate_run:
                logging.info("Starting locate")
                locate_run = True
                if self.cfg.locate:
                    w = self.createWorker(LocateWorker)
                

	if self.stop.isSet(): return

        if len(self.pathList) == 0:
            self.state_notify(NOTFOUND)
            return

        self.state_notify(WAITING)

        for w in self.workers:
            logging.info("%s %s" % (id(w), w.count))

    def run(self):
        self.mainJob()
        self.waitJobsEnd()
        while(self.any_worker_alive()):
            select.select([],[],[], 0.5)  
        
    def state_attach(self, ob):
        self.__state_observers.append(ob)

    def path_attach(self, ob):
        self.__path_observers.append(ob)
		
    def state_notify(self, state):
        self.state = state
        if state == INITIAL: return
        for o in self.__state_observers:
            o.state_update(self.state)

        if state == FULL:
            self.state_notify(WAITING)
            self.stop.set()

    def path_notify(self, path):

        # no listar el directorio actual
        if path == os.getcwd(): return   

        try:
            self.pathList.append(path)
        except PathList.AlreadyExistsException:
            return     

        try:
            for o in self.__path_observers:
                o.path_update(path)
        except self.FullException:
            self.state_notify(FULL)
            

            
    #private
    def any_worker_alive(self):
        #print '--', threading.activeCount()
        #print '\r-- ', self.workers
        #print '----------'
        #for i in self.workers: print i, i.isAlive()
        
        for i in self.workers:
            if i.isAlive(): return True
        return False


    def setElection(self, election):
        if self.state == NOTFOUND: return
        self.stop.set()
        if election == None:
            self.state_notify(CANCELED)
            return 

        self.dirname = self.pathList[election]

        if not os.path.exists(self.dirname):
            self.state_notify(NOTEXIST)
            return
            
        self.state_notify(FINISH)

        if self.cfg.cmd:
            cmd = self.cfg.cmd
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
    print '\rWarning: Ctrl-C ignored, to abort press ESC.'


def go2setup():
    if os.system('grep go2.sh ~/.bashrc > /dev/null') == 0:
        print('go2 already configured, skipping.')
        return 1

    os.system('echo "\n[ -e /usr/lib/go2/go2.sh ] && source /usr/lib/go2/go2.sh" >> ~/.bashrc')
    print('Setting up go2. It will be ready in next shell session.')
    return 0


def usage():
    prgname = os.path.splitext(os.path.basename(sys.argv[0]))[0]
    date = '$Date$' 
    version = date[9:17].replace('-','')
    #version = '$Rev: 1931 $'[6:-1]
    print '''%s version 0.%s, Copyright (C) 2007 David Villa Alises
go2 comes with ABSOLUTELY NO WARRANTY; This is free software, and you are
welcome to redistribute it under certain conditions; See COPYING for details.
''' % (prgname, version)

    print 'Usage: %s [options] <pattern>' % prgname
    print '''
options:
  -i            ignore case
  -r            search in whole file system
  -d            search into dot(hidden) folders also
  -H            list the history
  --gui         run in GUI mode
  --cmd <cmd>   exec this command instead of \'chdir\'
  --dir <dir>   search from this directory
'''
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
        self.flags = 0
        self.match_func = match_single
        self.pattern = None
        self.exclude = []
        self.cmd = None

        if not os.path.exists(GO2DIR):
            os.mkdir(GO2DIR)

        # load file specified excluded paths
        if os.path.exists(GO2EXCLUDE):
            fd = open(GO2EXCLUDE)
            lines = [i.strip() for i in fd.readlines()]
            self.exclude.extend([i for i in lines if i]) 
            fd.close()

        if self.exclude: logging.debug('exclude: %s' % self.exclude)
       
        try:
            opts, self.pattern = getopt.getopt(argv[1:], 'Hird',
                                               ['setup','no-locate', 'log', 'gui',
                                                'cmd=', 'dir='])
        except getopt.GetoptError:
            sys.exit(usage())

        for o, a in opts:
            if o == '-i':
                self.ignorecase = True
                self.flags |= re.IGNORECASE
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
            p = pathFile(GO2HISTORY)
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

        try:
            pass
            #re.match(self.re_pattern[0], '', self.flags)
        except re.error:
            raise self.NoValidPatternException


        

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
        

    def config(self):
        cfg = Config()
        cfg.pattern = self.wg_entry.get_text().split()
        cfg.parse_pattern()

        # switches
        cfg.from_root = self.wg_checkbutton_root.get_active()
        if self.wg_checkbutton_case.get_active():
            cfg.flags |= re.IGNORECASE
        else:
            cfg.flags &= ~ re.IGNORECASE

        cfg.process_hidden = not self.wg_checkbutton_hidden.get_active()

        cfg.cmd = self.wg_combo_cmd.child.get_text().strip()
        if cfg.cmd == 'chdir':
            cfg.cmd = None

    def main(self):
        gtk.main()

    def work(self):
        global manager

        try:
            self.config()
        except Config.EmptyPatternException:
            logging.debug('Falta diálogo de error, vacio')
            gobject.idle_add(self.gui_reset)
            return
        except Config.NoValidPatternException:
            logging.debug('Falta diálogo de error, no válido')
            return

        try:
            gobject.idle_add(self.gui_working)
            manager = Manager()
            manager.path_attach(self)
            manager.state_attach(self)
            manager.run()
        except AttributeError, e:
            print e
            
        #print 'fin de búsqueda'

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
        #self.work()

    def on_button_cancel_clicked(self, wd):
        manager.setElection(None)
        self.gui_reset()
       
    def on_button_clean_clicked(self, wd):
        self.gui_reset()

    def on_button_go_clicked(self, wd):
        #FIXME: controlar selección vacía
        self.config()
        model, it = self.selection.get_selected()
        manager.setElection(model[it][1])
        gtk.main_quit()

    def offline_path_update(self, path):
        tagged_path = re.sub('^' + os.environ['HOME'], '~',
                             highlight(Config().pattern,
                                       path, '<b>', '</b>',
                                       Config().flags))

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
            #self.wg_cancel.set_sensitive(False)
            #self.wg_clean.set_sensitive(True)
            #self.progressbar_text('Not found')

        if state == WAITING:
            logging.debug('WAITING')
            self.wg_button_search.set_sensitive(True)
            self.wg_button_cancel.set_sensitive(False)
            self.wg_button_clean.set_sensitive(True)
            self.progressbar_text('Ready: %d matches' % len(manager.pathList))

        if state == CANCELED:
            pass
            
        return False

    def state_update(self, state):
        gobject.idle_add(self.offline_state_update, state)
            


def console_main(argv):
    global manager

    try:
        Config(argv).parse_pattern()
    except Config.EmptyPatternException:
        sys.exit(usage())
    except Config.NoValidPatternException:
        print 'go2: invalid pattern', args
        sys.exit(1)

        
    manager = Manager()
    R = ConsoleUI()
    R.start()
    manager.run()
    R.join()



if __name__ == '__main__':

    argv = sys.argv[:]
    if os.path.exists(GO2CONFIG):
        argv[1:1]  = file(GO2CONFIG).read().split()

    if '--log' in argv:
        logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s %(levelname)-8s %(message)s',
                            filename=GO2LOG)
    else:
        logging.getLogger().setLevel(logging.CRITICAL)

    
    logging.info("---------- [go2 '%s']" % sys.argv[1:])

    #signal.signal(signal.SIGQUIT, leaveAdvice)
    #signal.signal(signal.SIGINT, leaveAdvice)
    #signal.signal(signal.SIGTERM, leaveAdvice)

    try: # Import Psyco if available
        import psyco
        psyco.full()
    except ImportError:
        logging.warning("psyco not available")


    has_DISPLAY = os.environ.has_key("DISPLAY")
    if not has_DISPLAY:
        logging.warning("$DISPLAY is not set, using console mode")

    if "--gui" in argv and has_DISPLAY:
        import gobject
        import gtk, gtk.glade
        gobject.threads_init()
        GtkFrontend(argv).main()
    else:
        console_main(argv)
        
