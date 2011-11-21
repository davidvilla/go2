#!/usr/bin/atheist
# -*- mode:python; coding:utf-8 -*-

import sys
import os
import time

import unittest2 as unittest
from fs.memoryfs import MemoryFS
from pyDoubles.framework import *
import gobject

import go2


def hello_task():
    return ["hi"]


class TestPool(unittest.TestCase):
    def setUp(self):
        self.pool = go2.ProcessPool()

    def test_create(self):
        self.pool.terminate()

    # Esta prueba no funciona con atheist
    def test_add_task_hello(self):
        self.pool.add_task(hello_task)

        self.assertEquals(self.pool.output_queue.get(timeout=1), "hi")

        self.pool.join()


class QueueReactor(object):
    class QueueExtractor(object):
        def __init__(self, queue, callback, *args):
            self.queue = queue
            self.callback = callback
            self.args = args

        def __call__(self):
            self.callback(self.queue.get(), *self.args)

    def add_queue_watch(self, queue, callback, *args):
        gobject.io_add_watch(queue._reader.fileno(),
                             gobject.IO_IN,
                             QueueExtractor(queue, callback, *args))

    def run(self):
        gobject.MainLoop().run()


class FilteredObserver(object):
    def __init__(self, queue):
        self.observers = []
        self.filters = []

    def notify(self, item):
        if any(f(item) for f in self.filters):
            return

        for ob in self.observers:
            ob(item)

    def register(self, ob):
        self.observer.append(ob)

    def add_filter(self, f):
        self.filters.append(f)


ui = UI()
path_list = PathList(ui.add_entry)

ob = FilteredObserver()
ob.add_filter(is_ignored)
ob.register(path_list.add)

queue = mp.Queue()

r = QueueReactor()
r.add_queue_watch(queue, ob.notify)
r.add_io_watch(stdin, ui.on_key_pressed)
r.run()


class TestIgnore(unittest.TestCase):
    def test_ignore_foo(self):
        go2.config = go2.get_config()
        go2.config.ignore = ['foo']

        path_ob = PathObserver()

        reactor.add(path_ob)
        reactor.run()
