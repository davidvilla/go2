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
    

import threading
import os, sys, tty, termios, select, re
import subprocess
import signal
import string
import time
import logging
import getopt


ESC = 27
ENTER = 13

#FILES
GO2DIR =     os.path.join(os.environ['HOME'], '.go2')
GO2IGNORE =  os.path.join(GO2DIR, 'ignore')
GO2HISTORY = os.path.join(GO2DIR, 'history')
GO2CACHE =   os.path.join(GO2DIR, 'cache')
GO2TMP =     os.path.join(GO2DIR, 'tmp')
GO2LOG =     os.path.join(GO2DIR, 'log')



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
    return re.match(opt.re_pattern[0], os.path.basename(path), opt.flags)

def match_multi(path):
    "path must be a abspath"

    items = path.split(os.sep)[1:]
    pattern = opt.re_pattern

    match = re.match(pattern[-1], items[-1], opt.flags)
    if not match: return False

    p = len(pattern) - 2
    for i in items[-2::-1]:
        if p < 0: return True
        if re.match(pattern[p], i, opt.flags): p -= 1

    return False


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
    def __init__(self):
	threading.Thread.__init__(self, name='Reader')
	self.file = sys.stdin
	self.matches = 0
        self.state = None
        manager.attach(self)

    def __del__(self):
	self.ttyrestore()

    def ttyrestore(self):
        tty.tcsetattr(self.file, termios.TCSADRAIN, self.old_settings)

    def run(self):
	#self.ttyraw()
        self.old_settings = tty.tcgetattr(self.file)
        tty.setraw(self.file)
        po = select.poll()
        po.register(self.file, select.POLLIN)
        election = None
       
	while 1:
            if len(po.poll(250)) == 0:
                if self.state == Manager.NOTFOUND:
                    break
                
                elif self.state == Manager.WAITING and self.matches == 1:
                    key = ENTER

                else:                
                    continue
            else:
                key = ord(self.file.read(1))

	    if key == ESC:
		election = None
		break

            if key == ENTER:
                election = 0
            else:
                election = key - ord('a')
			
	    if election in range(0, self.matches):
		break

        self.ttyrestore()
        self.mgr.setElection(election)

    def update(self, state):
	self.matches = len(self.mgr.pathList)
        self.state = state


class Reader(threading.Thread):
    def __init__(self, mgr):
	threading.Thread.__init__(self, name='Reader')
	self.mgr = mgr
	self.file = sys.stdin
	self.matches = 0
	self.mgr.attach(self)
        self.state = None

    def __del__(self):
	self.ttyrestore()

    def ttyrestore(self):
        tty.tcsetattr(self.file, termios.TCSADRAIN, self.old_settings)

    def run(self):
	#self.ttyraw()
        self.old_settings = tty.tcgetattr(self.file)
        tty.setraw(self.file)
        po = select.poll()
        po.register(self.file, select.POLLIN)
        election = None
       
	while 1:
            if len(po.poll(250)) == 0:
                if self.state == Manager.NOTFOUND:
                    break
                
                elif self.state == Manager.WAITING and self.matches == 1:
                    key = ENTER

                else:                
                    continue
            else:
                key = ord(self.file.read(1))

	    if key == ESC:
		election = None
		break

            if key == ENTER:
                election = 0
            else:
                election = key - ord('a')
			
	    if election in range(0, self.matches):
		break

        self.ttyrestore()
        self.mgr.setElection(election)

    def update(self, state):
	self.matches = len(self.mgr.pathList)
        self.state = state


class UI:

    high = chr(27)+'[1m'
    low = chr(27)+'[m'
	
    def __init__(self):
	self.last_ = 0
	self.index_ = ord('a')
	manager.attach(self)


    def highlight(self, path):
        items = path.split(os.sep)
        pattern = opt.pattern
        
        p = len(pattern) - 1
        for i in range(len(items)-1,-1,-1):
            if p < 0: break
            if re.match(pattern[p], items[i], opt.flags):
                orig = items[i][:len(pattern[p])]
                items[i] = re.sub(orig,
                                  self.high + orig + self.low,
                                  items[i], 1)
                p -= 1
                
        retval = os.sep.join(items)
        return retval
        
	
    def update(self, state):
        msg_select = '\rSelect a path: '
	print ('\r' + ' '*len(msg_select)),
		
	if state == Manager.WAITING:
	    print '\rSelect a path: ',
	elif state == Manager.CANCELED:
	    print '\rCanceled by user'
	elif state == Manager.NOTFOUND:
            logging.info("Pattern doesn't match")
	    print "\rPattern doesn't match\r"
	elif state == Manager.FULL:
            logging.warning('Warning: Too many matches')
	    print '\rWarning: Too many matches!'
	elif state == Manager.FINISH:
	    print "\rChanging to: %s%s%s" % \
                    (self.high, manager.dirname, self.low)
	elif state == Manager.WORKING:

	    newSize = len(manager.pathList)
            for path in manager.pathList[self.last_:newSize]:
                
                # usar string.replace en lugar de re.sub??
		path = re.sub('^' + os.environ['HOME'], '~',
                              self.highlight(path))
                
		print "\r%c: %s" % (chr(self.index_),
                                    path)
                self.index_ += 1

            print '\rSearching...',
            self.last_ = newSize
	else:
	    print "\rInternal ERROR: unknown state '%d'\n" % state
		

class PathList:

    class FullException: pass
    def __init__(self, maxSize=26):
        self.data = []
        self.maxSize = maxSize
        self.lock = threading.Lock()

    def append(self, item):
        if item in self.data: return
        if self.isFull(): return

        logging.debug("PathList[%s]: %s" % (len(self), item))
        self.lock.acquire()
        self.data.append(item)
        self.lock.release()

        if self.isFull():
            logging.debug('Is full: %s' % len(self))
            raise self.FullException
       

    def __getitem__(self, index):
        return self.data[index]

    def __len__(self):
        return len(self.data)

    def isFull(self):
        return len(self.data) > self.maxSize


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

        if not opt.process_hidden:
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

    def __init__(self, root, ignList):
        threading.Thread.__init__(self) #, name = "Worker %d" % self.i)
#        self.i += 1
        self.root = root
        self.ignList = ignList
        self.count = 0

    def update(*args):
        pass

    def not_ignore(self, path):
        # Comprueba que la ruta absoluta 'path' no está excluida FIXME:
        # Comprobar también que el nombre de directorio no está excluido
        # (ej.svn)
        for p in self.ignList:
            if path.startswith(p): return False
        return True

class LocateWorker(Worker):
    "Parse locate output"
    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)

    def run(self):
        options = '-l 1000 -e -b '
        if opt.flags | re.IGNORECASE:
            options += '-i '
        cmd = 'locate %s %s' % (options, opt.pattern[0])
        logging.info('locate cmd: %s' % cmd)

        # FIXME: puede que locate no exista
        locate = subprocess.Popen(cmd, shell=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  close_fds=True)

        rules = PathAsserts()
        if not opt.process_hidden: rules.add(not_hidden)
        if not opt.from_root:      rules.add(is_local)
        rules.add(os.path.isdir)
        if self.ignList:           rules.add(self.not_ignore)
        rules.add(opt.matches)

        for i in locate.stdout:
            if manager.stop.isSet():
                os.kill(locate.pid, signal.SIGKILL)
                return

            i = i.strip('\n')
            logging.debug("locate-> '%s'" % i)
            
            if not rules.test(i): continue
            manager.notify(path=i)



class HistoryWorker(Worker):
    "Search in directories selected some time"

    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)
        self.fname = kargs['fname']
        self.drop = []

    def run(self):
        self.pFile = pathFile(self.fname, 500)
        for i in self.pFile.data:
            if manager.stop.isSet(): return

            mdebug ("\r\n-> '%s'" % i)
            if opt.matches(i):
                if not os.path.exists(i):
                    self.drop.append(i)
                    continue

                mdebug(" [OK]")
                manager.notify(path=i)

            mdebug("\n")


    def update(self, state):
        if state != Manager.FINISH: return
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

    def run(self):
        self.pFile = pathFile(self.fname, 1000)
        logging.info('cache len:' + str(len(self.pFile.data)))

        for i in self.pFile.data:
            if manager.stop.isSet(): return

            if opt.matches(i):
                if not os.path.exists(i):
                    self.drop.append(i)
                    continue

                mdebug(" [OK]")
                manager.notify(path=i)

            mdebug("\n")

	
    def update(self, state):
        if state == Manager.WORKING:
            newSize = len(manager.pathList)
            for path in manager.pathList[self.last_:newSize]:
                self.pFile.insert(path)
	    self.last_ = newSize

        elif state == Manager.FINISH:
            for i in self.drop: self.pFile.data.remove(i)
            self.pFile.commit()


class DiskWorker(Worker):

    def __init__(self, *args, **kargs):
        Worker.__init__(self, *args)
        logging.info("[%s] New DiskWorker for '%s'" % (id(self), self.root))

    def run(self):

        rules = PathAsserts()
        if not opt.process_hidden: rules.add(not_hidden)
        if self.ignList:           rules.add(self.not_ignore)
        
        for root, dirs, files in os.walk(self.root):
            if manager.stop.isSet(): return

            if len(dirs) == 0: continue

            for d in list(dirs):
                #print d
                path = os.path.join(root, d)
                #if (d[0] == '.' and not opt.process_hidden) or \
                #    d in self.ignList or path in self.ignList:
                if not rules.test(path):
                    dirs.remove(d)
                    continue

                #print '\r\n', os.path.basename(path), path,
                #if os.path.basename(path) == "repos":
                #    print 'SINGLE', path

                if opt.matches(path):
                    manager.notify(path=path)
                    self.count += 1
                elif opt.matches == match_multi and match_single(path):
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
            manager.notify(path=path)


class Manager:

    INITIAL,  WORKING, WAITING, CANCELED, \
    NOTFOUND, FINISH,  FULL,    NOTEXIST = range(8)

    def __init__(self, ignList):
        self.pathList = PathList(26)
        self.__observers = []
        
        if opt.parent_mode:
            self.mainJob = self.parentMode_job
        elif opt.history_mode:
            self.mainJob = self.historyMode_job
			
        self.ignList = ignList
        self.workers = []
	self.stop = threading.Event()
        self.state = self.INITIAL

        self.tinit = time.time()

    def createWorker(self, workerClass, root = None, **kargs):
        if self.stop.isSet(): return None

        if root:
            ignList_cp = [x for x in self.ignList if not root.startswith(x)]
            self.ignList.append(root)
        else:
            ignList_cp = self.ignList[:]

        #print root, ignList_cp

        w = workerClass(root, ignList_cp, **kargs)
        self.workers.append(w)
        self.attach(w)
        w.start()
        return w

    def parentMode_job(self):
        self.createWorker(ParentWorker)
        self.notify(self.WORKING)

    def historyMode_job(self):
        print 'go2: history mode'
        self.createWorker(HistoryWorker, fname = GO2HISTORY)
        self.notify(self.WORKING)


    def mainJob2(self):
        self.notify(self.WORKING)
        
        dirs = list(set([os.getcwd()]))
        for target in dirs:
            self.createWorker(DiskWorker, target)


    def mainJob(self):
        w = self.createWorker(HistoryWorker, fname = GO2HISTORY)
        if w: w.join(1)
        
        self.notify(self.WORKING)

        # si el patrón es el nombre de un subdirectorio de pwd
        if len(opt.pattern) == 1 and os.path.isdir(opt.pattern[0]):
            self.notify(path = os.path.abspath(opt.pattern[0]))

        w = self.createWorker(CacheWorker, fname = GO2CACHE)
        if w: w.join(1)
        
        dirs = list(set([os.getcwd(), os.environ['HOME']]))
        #dirs = list(set([os.getcwd()]))

        if opt.from_root:
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
                if opt.locate:
                    w = self.createWorker(LocateWorker)
                

	if self.stop.isSet(): return

        if len(self.pathList) == 0:
            self.notify(self.NOTFOUND)
            return

        self.notify(self.WAITING)

        for w in self.workers:
            logging.info("%s %s" % (id(w), w.count))

    def run(self):
        self.mainJob()
        self.waitJobsEnd()
        while(self.any_worker_alive()):
            select.select([],[],[], 0.5)  
        
    def attach(self, observer):
        self.__observers.append(observer)
		
    def notify(self, state=None, path=None):
        #if self.stop.isSet(): return

        if state == None:
            try:
                self.pathList.append(path)
            except PathList.FullException:
                manager.notify(Manager.FULL)
                return
        else:
            self.state = state
        
        if self.state == self.INITIAL: return
        for o in self.__observers: o.update(self.state)

        if state == self.FULL:
            self.notify(self.WAITING)
            self.stop.set()
            
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
        if self.state == self.NOTFOUND: return
        self.stop.set()
        if election == None:
            self.notify(self.CANCELED)
            return 

        self.dirname = self.pathList[election]

        if not os.path.exists(self.dirname):
            self.notify(self.NOTEXIST)
            return
            
        self.notify(self.FINISH)
        saveTarget(self.dirname)
        

def leaveAdvice(*args):
    print '\rWarning: Ctrl-C ignored, to abort press ESC.'

def userConfig(ignList):
    if not os.path.exists(GO2DIR):
        os.mkdir(GO2DIR)

    # load file specified ignored paths
    if os.path.exists(GO2IGNORE):
        fd = open(GO2IGNORE)
        lines = [i.strip() for i in fd.readlines()]
        ignList.extend([i for i in lines if i]) 
        fd.close()

    if ignList: logging.debug('ignore: %s' % ignList)

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

def main():
    global manager

    try: # Import Psyco if available
        import psyco
        psyco.full()
    except ImportError:
        pass
    
    ignoreList = []

    userConfig(ignoreList)

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        filename=GO2LOG)
    
    logging.info("---------- [go2 '%s']" % sys.argv[1:])

    #signal.signal(signal.SIGQUIT, leaveAdvice)
    #signal.signal(signal.SIGINT, leaveAdvice)
    #signal.signal(signal.SIGTERM, leaveAdvice)

    manager = Manager(ignoreList)
    UI()
    R = Reader(manager)
    R.start()
    manager.run()
    R.join()


class Options:
    def __init__(self):

        self.history_mode = False
        self.parent_mode = False
        self.from_root = False
        self.process_hidden = False
        self.locate = True
        self.flags = 0
        self.matches = match_single

        try:
            opts, args = getopt.getopt(sys.argv[1:], 'Hird', ['setup','no-locate'])
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


        if not args:
            sys.exit(usage())
        
        self.pattern = args
    
        if self.pattern[0] == '..':
            self.parent_mode = True
            self.pattern = ['']

        self.re_pattern = ['^' + x for x in self.pattern]

        if len(self.pattern) > 1:
            self.matches = match_multi

        try:
            re.match(self.re_pattern[0], '', self.flags)
        except re.error:
            print 'go2: invalid pattern', args
            sys.exit(1)


if __name__ == '__main__':
    opt = Options()
    main()        
    sys.exit(0)

