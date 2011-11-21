#!/usr/bin/atheist
# -*- mode:python; coding:utf-8 -*-

import sys
import os
import time
import multiprocessing as mp

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


class TestIgnore(unittest.TestCase):
    def atest_ignore_foo(self):
        go2.config = go2.get_config()
        go2.config.ignore = ['foo']

        path_ob = PathObserver()

        reactor.add(path_ob)
        reactor.run()


class Test_FilteredObserver(unittest.TestCase):
    def observable_with_observer(self):
        self.ob = empty_mock()
        self.sut = go2.FilteredObservable()
        self.sut.register(self.ob.update)

    def test_update(self):
        self.observable_with_observer()
        expect_call(self.ob.update).with_args('foo')

        self.sut.notify('foo')

        self.ob.assert_expectations()

    def test_filter(self):

        def foo_filter(value):
            return value == 'foo'

        self.observable_with_observer()
        expect_call(self.ob.update).with_args('bar')
        self.sut.add_filter(foo_filter)

        self.sut.notify('foo')
        self.sut.notify('bar')

        self.ob.assert_that_is_satisfied()


class Test_QueueReactor(unittest.TestCase):
    def test_put(self):
        # given:
        ob = empty_mock()
        expect_call(ob.update)

        queue = mp.Queue()
        queue.put('foo')

        sut = go2.QueueReactor()
        sut.queue_add_watch(queue, ob.update)

        # when
        sut.process_pending()

        # then
        ob.assert_that_is_satisfied()
