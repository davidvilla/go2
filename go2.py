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

import gobject, gtk, gtk.glade
gobject.threads_init()

ESC = 27
ENTER = 13

#FILES
GO2DIR =     os.path.join(os.environ['HOME'], '.go2')
GO2EXCLUDE =  os.path.join(GO2DIR, 'exclude')
GO2HISTORY = os.path.join(GO2DIR, 'history')
GO2CACHE =   os.path.join(GO2DIR, 'cache')
GO2CONFIG =  os.path.join(GO2DIR, 'config') 
GO2TMP =     os.path.join(GO2DIR, 'tmp')
GO2LOG =     os.path.join(GO2DIR, 'log')


# states
INITIAL,  WORKING, WAITING, CANCELED, \
NOTFOUND, FINISH,  FULL,    NOTEXIST = range(8)


#class SyncFile:
#    def __init__(self, fd):
#        self.fd = fd
#    def write(self, data):
#        self.fd.write(data)
#        self.fd.flush()
#    def flush(self):
#        self.fd.flush()
#
#sys.stdout = SyncFile(sys.stdout)
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

def debug(*args): pass
mdebug = debug
#mdebug = sys.stdout.write

#-- path checkers
def not_hidden(path):
    return not ((os.sep + '.') in path)

def has_dot(path):
    return (os.sep + '.') in path

def is_local(path):
    return path.startswith(os.environ['HOME'])

#--



def filterout_hidden(pathlist):
    return [x for x in pathlist if not has_dot(x)]

def match_single(path):
    return re.match(manager.opt.re_pattern[0],
                    os.path.basename(path),
                    manager.opt.flags)

def match_multi(path):
    "path must be a abspath"

    items = path.split(os.sep)[1:]
    pattern = manager.opt.re_pattern

    match = re.match(pattern[-1], items[-1], manager.opt.flags)
    if not match: return False

    p = len(pattern) - 2
    for i in items[-2::-1]:
        if p < 0: return True
        if re.match(pattern[p], i, manager.opt.flags): p -= 1

    return False



def highlight(pattern, path, before, after, flags=0):
    items = path.split(os.sep)
    
    p = len(pattern) - 1
    for i in range(len(items)-1,-1,-1):
        if p < 0: break
        if re.match(pattern[p], items[i], flags):
            orig = items[i][:len(pattern[p])]
            items[i] = re.sub(orig,
                              before + orig + after,
                              items[i], 1)
            p -= 1
            
    retval = os.sep.join(items)
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
            if not f(path): return False

        return True
        

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

#    @classmethod
#    def highlight(self, path):
#        items = path.split(os.sep)
#        pattern = opt.pattern
#        
#        p = len(pattern) - 1
#        for i in range(len(items)-1,-1,-1):
#            if p < 0: break
#            if re.match(pattern[p], items[i], opt.flags):
#                orig = items[i][:len(pattern[p])]
#                items[i] = re.sub(orig,
#                                  self.HIGH + orig + self.LOW,
#                                  items[i], 1)
#                p -= 1
#                
#        retval = os.sep.join(items)
#        return retval

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

        #print 'n-->', self.__matches
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

        assert  manager.state == WORKING

        path = re.sub('^' + os.environ['HOME'], '~',
                      highlight(manager.opt.pattern,
                                path, self.HIGH, self.LOW, manager.opt.flags))
                
        print "\r%c: %s" % (chr(self.__index), path)
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


class pathFile:
    "Manage a file which content a path set"
    def __init__(self, filename, size = 100):
        self.data = []
        self.filename = filename
        self.size = size
        if os.path.exists(filename): 
            fd = open(filename)
            self.data = [x.strip('\n') for x in fd.readlines()]
            fd.close()

        if not manager.opt.process_hidden:
            self.data = filterout_hidden(self.data)

    def insert(self, item):
        logging.debug("saving to file: %s (%s)" % (item, str(len(self.data))))
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
        self.exclude = exclude
        self.count = 0

    def not_exclude(self, path):
        # Comprueba que la ruta absoluta 'path' no está excluida FIXME:
        # Comprobar también que el nombre de directorio no está excluido
        # (ej.svn)
        for p in self.exclude:
            if path.startswith(p): return False
        return True

class LocateWorker(Worker):
    "Parse locate output"
    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)

    def run(self):
        options = '-l 1000 -e -b '
        if manager.opt.flags | re.IGNORECASE:
            options += '-i '
        cmd = 'locate %s %s' % (options, manager.opt.pattern[0])
        logging.info('locate cmd: %s' % cmd)

        # FIXME: puede que locate no exista
        locate = subprocess.Popen(cmd, shell=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  close_fds=True)

        rules = PathAsserts()
        if not manager.opt.process_hidden: rules.add(not_hidden)
        if not manager.opt.from_root:      rules.add(is_local)
        rules.add(os.path.isdir)
        if self.exclude:           rules.add(self.not_exclude)
        rules.add(manager.opt.match_func)

        for i in locate.stdout:
            if manager.stop.isSet():
                os.kill(locate.pid, signal.SIGKILL)
                return

            i = i.strip('\n')
            logging.debug("locate-> '%s'" % i)
            
            if not rules.test(i): continue
            manager.path_notify(i)



class HistoryWorker(Worker):
    "Search in directories selected some time"

    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)
        self.fname = kargs['fname']
        self.drop = []
        manager.state_attach(self)

    def run(self):
        self.pFile = pathFile(self.fname, 500)
        for i in self.pFile.data:
            if manager.stop.isSet(): return

            mdebug ("\r\n-> '%s'" % i)
            if manager.opt.match_func(i):
                if not os.path.exists(i):
                    self.drop.append(i)
                    continue

                mdebug(" [OK]")
                manager.path_notify(i)

            mdebug("\n")


    def state_update(self, state):
        if state != FINISH: return
        for i in self.drop:
            self.pFile.data.remove(i)
        self.pFile.insert(manager.dirname)
        self.pFile.commit()


class CacheWorker(Worker):

    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)
        self.fname = kargs['fname']
        self.last_ = 0
        self.drop = []
        manager.state_attach(self)

    def run(self):
        self.pFile = pathFile(self.fname, 1000)
        logging.info('cache len:' + str(len(self.pFile.data)))

        for i in self.pFile.data:
            if manager.stop.isSet(): return

            if manager.opt.match_func(i):
                if not os.path.exists(i):
                    self.drop.append(i)
                    continue

                mdebug(" [OK]")
                manager.path_notify(i)

            mdebug("\n")

	
    def state_update(self, state):
        if state == WORKING:
            newSize = len(manager.pathList)
            for path in manager.pathList[self.last_:newSize]:
                self.pFile.insert(path)
	    self.last_ = newSize

        elif state == FINISH:
            for i in self.drop: self.pFile.data.remove(i)
            self.pFile.commit()


class DiskWorker(Worker):

    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)
        logging.info("[%s] New DiskWorker for '%s'" % (id(self), self.root))

    def run(self):

        rules = PathAsserts()
        if not manager.opt.process_hidden: rules.add(not_hidden)
        if self.exclude:           rules.add(self.not_exclude)
        
        for root, dirs, files in os.walk(self.root):
            if manager.stop.isSet(): return

            if len(dirs) == 0: continue

            for d in list(dirs):
                #print d
                path = os.path.join(root, d)
                #if (d[0] == '.' and not opt.process_hidden) or \
                #    d in self.exclude or path in self.exclude:
                if not rules.test(path):
                    dirs.remove(d)
                    continue

                #print '\r\n', os.path.basename(path), path,
                #if os.path.basename(path) == "repos":
                #    print 'SINGLE', path

                if manager.opt.match_func(path):
                    manager.path_notify(path)
                    self.count += 1
                elif manager.opt.match_func == match_multi and match_single(path):
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


class Manager:

    class FullException: pass

    def __init__(self, opt):
        self.pathList = PathList()
        self.__observers = []
        self.__state_observers = []
        self.__path_observers = []
        
        if opt.parent_mode:
            self.mainJob = self.parentMode_job
        elif opt.history_mode:
            self.mainJob = self.historyMode_job

        self.opt = opt
        self.workers = []
	self.stop = threading.Event()
        self.state = INITIAL

        self.tinit = time.time()

    def createWorker(self, workerClass, root = None, **kargs):
        if self.stop.isSet(): return None

        if root:
            exclude_cp = [x for x in self.opt.exclude if not root.startswith(x)]
            self.opt.exclude.append(root)
        else:
            exclude_cp = self.opt.exclude[:]

        #print root, exclude_cp

        w = workerClass(root, exclude_cp, **kargs)
        self.workers.append(w)
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
        if len(manager.opt.pattern) == 1 and os.path.isdir(manager.opt.pattern[0]):
            self.path_notify(os.path.abspath(manager.opt.pattern[0]))

        w = self.createWorker(CacheWorker, fname = GO2CACHE)
        if w: w.join(1)
        
        dirs = list(set([os.getcwd(), os.environ['HOME']]))
        #dirs = list(set([os.getcwd()]))

        if manager.opt.from_root:
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
                logging.info("Arrancando locate.")
                locate_run = True
                if manager.opt.locate:
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
        
    def attach(self, observer):
        self.__observers.append(observer)

    def state_attach(self, ob):
        self.__state_observers.append(ob)

    def path_attach(self, ob):
        self.__path_observers.append(ob)
		
#    def notify(self, state=None, path=None):
#        #if self.stop.isSet(): return
#
#        if state == None:
#            try:
#                self.pathList.append(path)
#            except PathList.FullException:
#                self.notify(FULL)
#                return
#            except PathList.AlreadyExistsException:
#                return
#        else:
#            self.state = state
#        
#        if self.state == self.INITIAL: return
#        for o in self.__observers: o.update(self.state, path)
#
#        if state == self.FULL:
#            self.notify(self.WAITING)
#            self.stop.set()


    def state_notify(self, state):
        self.state = state
        if state == INITIAL: return
        for o in self.__state_observers:
            o.state_update(self.state)

        if state == FULL:
            self.state_notify(WAITING)
            self.stop.set()

    def path_notify(self, path):
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

        if self.opt.cmd:
            cmd = self.opt.cmd
            if '%d' in cmd:
                cmd = cmd.replace('%d', '%s')
                cmd = cmd % self.dirname
           
            print "command is: '%s'" % cmd
            cmdlist = cmd.split()
            os.chdir(self.dirname)
            os.execvp(cmdlist[0], cmdlist)
        else:
            saveTarget(self.dirname)
        

def leaveAdvice(*args):
    print '\rWarning: Ctrl-C ignored, to abort press ESC.'


def go2setup():
    if os.system('grep go2.sh ~/.bashrc > /dev/null') == 0:
        print('go2 was setup before, nothing to do.')
        return 1

    os.system('echo "[ -e /usr/lib/go2/go2.sh ] && source /usr/lib/go2/go2.sh" >> ~/.bashrc')
    print('Setting up go2. It will be usable in next shell session.')
    return 0


def usage():
    prgname = os.path.splitext(os.path.basename(sys.argv[0]))[0]
    date = '$Date: 2007-03-11 17:55:29 +0100 (dom, 11 mar 2007) $'
    version = date[9:17].replace('-','')
    #version = '$Rev: 1931 $'[6:-1]
    print '''%s version 0.%s, Copyright (C) 2004, 2005, 2006 David Villa Alises
go2 comes with ABSOLUTELY NO WARRANTY; This is free software, and you are
welcome to redistribute it under certain conditions; See COPYING for details.
''' % (prgname, version)

    print 'Usage: %s [options] <pattern>' % prgname
    print '''
options:
  -i:       ignore case
  -r:       search from root directory too
  -d:       search into dot(hidden) folders
  -H:       list the history
'''
    return 1



################################


class Config:
    
    class NoValidPatternException: pass
    
    def __init__(self, argv):
        self.history_mode = False
        self.parent_mode = False
        self.from_root = False
        self.process_hidden = False
        self.locate = True
        self.flags = 0
        self.match_func = match_single
        self.pattern = None
        self.exclude = []
        self.cmd = None

        # run follows first time only
#        self.initial = False
#        if self.initial: return
#        self.initial = True

        if not os.path.exists(GO2DIR):
            os.mkdir(GO2DIR)

        if os.path.exists(GO2CONFIG):
            config = open(GO2CONFIG)
            argv[1:1] = config.read().split()
            config.close()

        # load file specified excluded paths
        if os.path.exists(GO2EXCLUDE):
            fd = open(GO2EXCLUDE)
            lines = [i.strip() for i in fd.readlines()]
            self.exclude.extend([i for i in lines if i]) 
            fd.close()

        if self.exclude: logging.debug('exclude: %s' % self.exclude)


        print argv
        
        try:
            opts, self.pattern = getopt.getopt(argv[1:], 'Hird',
                                               ['setup','no-locate', 'cmd='])
        except getopt.GetoptError:
            sys.exit(usage())

        for o, a in opts:
            if o == '-i':
                self.flags |= re.IGNORECASE
            if o == '-r':
                self.from_root = True
            if o == '-d':
                self.process_hidden = True
            if o == '-H':
                self.history_mode = True
                self.pattern = ['']    # hack para que todos hagan matching
                self.re_pattern = self.pattern
                return
            if o == '--no-locate':
                self.locate = False
            if o == '--setup':
                sys.exit(go2setup())
            if o == '--cmd':
                self.cmd = a



class CmdLineConfig(Config):
    def __init__(self, argv):
        Config.__init__(self, argv)

    def parse_pattern(self):
        if not self.pattern:
            sys.exit(usage())
    
        if self.pattern[0] == '..':
            self.parent_mode = True
            self.pattern = ['']

        self.re_pattern = ['^' + x for x in self.pattern]

        if len(self.pattern) > 1:
            self.match_func = match_multi

        try:
            re.match(self.re_pattern[0], '', self.flags)
        except re.error:
            print 'go2: invalid pattern', args
            sys.exit(1)


class GuiConfig(Config):
    def __init__(self, argv, glade):
        Config.__init__(self, argv)
        
        self.pattern = glade.get_widget('entry').get_text().split()
        if not self.pattern:
            raise self.NoValidPatternException
        
        self.re_pattern = ['^' + x for x in self.pattern]

        # switches
        self.from_root = glade.get_widget('checkbutton_root').get_active()
        if glade.get_widget('checkbutton_case').get_active():
            self.flags |= re.IGNORECASE
        else:
            self.flags &= ~ re.IGNORECASE

        if not glade.get_widget('checkbutton_hidden').get_active():
            self.process_hidden = True

class GtkFrontend:
    def __init__(self, argv):
        self.argv = argv
        
        self.glade = gtk.glade.XML('go2.glade2')
        self.glade.signal_autoconnect(self)

        self.window = self.glade.get_widget('window')
        self.wg_entry = self.glade.get_widget('entry')
        self.wg_search = self.glade.get_widget('button_search')
        self.wg_stop =  self.glade.get_widget('button_stop')
        self.wg_clean =  self.glade.get_widget('button_clean')
        self.wg_go = self.glade.get_widget('button_go')


        # setup treeview
        self.wg_treeview = self.glade.get_widget('treeview')
        self.store = gtk.ListStore(str, int)
        self.wg_treeview.set_model(self.store)

        self.cell = gtk.CellRendererText()
        
        self.tvcolumn = gtk.TreeViewColumn('Path', self.cell, markup=0)
        self.tvcolumn.set_sort_column_id(0)
        #self.tvcolumn.pack_start(self.cell, True)
        #self.tvcolumn.add_attribute(self.cell, 'text', 0)

        self.wg_treeview.append_column(self.tvcolumn)
        self.selection = self.wg_treeview.get_selection()
        self.selection.set_mode(gtk.SELECTION_SINGLE)

        self.__n = 0


    def main(self):
        gtk.main()

    def all(self):
        global manager

        #self.wg_search.set_sensitive(True)
        #FIXME: activar barra de progreso

        try:
            opt = GuiConfig(self.argv[:], self.glade)
        except Config.NoValidPatternException:
            self.gui_reset()
            return
        
        manager = Manager(opt)
        manager.path_attach(self)
        manager.state_attach(self)
        manager.run()
        print 'fin de búsqueda'

    def gui_reset(self):
        self.wg_entry.set_text('')
        self.wg_entry.grab_focus()
        self.wg_search.set_sensitive(True)
        self.store.clear()
        self.wg_stop.set_sensitive(False)
        self.wg_clean.set_sensitive(False)
        self.wg_go.set_sensitive(False)

    def gui_working(self):
        self.wg_search.set_sensitive(False)
        self.wg_stop.set_sensitive(True)
        self.wg_clean.set_sensitive(False)
        self.wg_go.set_sensitive(False)

    def on_window_delete_event(self, *args):
        gtk.main_quit()

    def on_button_search_clicked(self, wd):
        thread.start_new_thread(self.all, ())
        self.store.clear()
        self.gui_working()
        
    def on_button_stop_clicked(self, wd):
        manager.stop.set()
        self.wg_search.set_sensitive(True)
        self.wg_stop.set_sensitive(False)
        self.wg_clean.set_sensitive(True)
        self.wg_go.set_sensitive(True)

    def on_button_clean_clicked(self, wd):
        self.gui_reset()

    def on_button_go_clicked(self, wd):
        #FIXME: controlar selección vacía
        model, it = self.selection.get_selected()
        manager.setElection(model[it][1])
        gtk.main_quit()


    def offline_path_update(self, path):
        #if state == manager.FINISH:
        #    self.stop = True

        tagged_path = re.sub('^' + os.environ['HOME'], '~',
                             highlight(manager.opt.pattern,

                                       path, '<b>', '</b>',
                                       manager.opt.flags))

        self.store.append([tagged_path, self.__n])
        self.__n += 1
        return False
    
    def path_update(self, path):
        gobject.idle_add(self.offline_path_update, path)

    def offline_state_update(self, state):
        print state
        if state == WAITING:
            print 'WAITING'
            self.wg_stop.set_sensitive(False)
            self.wg_search.set_sensitive(True)
            self.wg_treeview.grab_focus()
            self.wg_clean.set_sensitive(True)            
            self.wg_go.set_sensitive(True)

        if state == NOTFOUND:
            print 'NOTFOUND'
            self.gui_reset()

        if state == CANCELED:
            print 'CANCELED'
            
        return False

    def state_update(self, state):
        gobject.idle_add(self.offline_state_update, state)
            


def console_main(argv):
    global manager

    opt = CmdLineConfig(argv)
    opt.parse_pattern()
    manager = Manager(opt)
    R = ConsoleUI()
    R.start()
    manager.run()
    R.join()



if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        filename=GO2LOG)
    
    logging.info("---------- [go2 '%s']" % sys.argv[1:])

    #signal.signal(signal.SIGQUIT, leaveAdvice)
    #signal.signal(signal.SIGINT, leaveAdvice)
    #signal.signal(signal.SIGTERM, leaveAdvice)

    try: # Import Psyco if available
        import psyco
        psyco.full()
    except ImportError:
        logging.warning("psyco not available")


    if "--gui" in sys.argv:
        argv = [x for x in sys.argv if x != "--gui"]
        GtkFrontend(argv).main()
    else:
        console_main(sys.argv)

