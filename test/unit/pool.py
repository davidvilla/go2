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


def foo_filter(value):
    return value == 'foo'


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


# class TestIgnore(unittest.TestCase):
#     def atest_ignore_foo(self):
#         go2.config = go2.get_config()
#         go2.config.ignore = ['foo']
#
#         path_ob = PathObserver()
#
#         reactor.add(path_ob)
#         reactor.run()


# class Test_FilteredObserver(unittest.TestCase):
#     def observable_with_observer(self):
#         self.ob = empty_mock()
#         self.sut = go2.FilteredObservable()
#         self.sut.register(self.ob.update)
#
#     def test_update(self):
#         self.observable_with_observer()
#         expect_call(self.ob.update).with_args('foo')
#
#         self.sut.notify('foo')
#
#         self.ob.assert_that_is_satisfied()
#
#     def test_filter(self):
#
#         def foo_filter(value):
#             return value == 'foo'
#
#         self.observable_with_observer()
#         expect_call(self.ob.update).with_args('bar')
#         self.sut.add_filter(foo_filter)
#
#         self.sut.notify('foo')
#         self.sut.notify('bar')
#
#         self.ob.assert_that_is_satisfied()


class Test_QueueReactor(unittest.TestCase):
    def setUp(self):
        self.sut = go2.QueueReactor()

    def test_queue_add_watch(self):
        # given:
        queue = mp.Queue()
        queue.put('foo')

        handler = empty_mock()
        expect_call(handler.handle).with_args(ANY_ARG, gobject.IO_IN, queue).then_return(False)

        self.sut.queue_add_watch(queue, handler.handle)

        # when
        time.sleep(0.1)
        self.sut.process_pending()

        # then
        handler.assert_that_is_satisfied()

    def test_quit(self):
        # given
        gobject.timeout_add(1, self.sut.quit)

        # when
        self.sut.run()

        # then
        # reach this


class Test_PathStorage(unittest.TestCase):
    def setUp(self):
        self.path = '/usr/share'

    def test_add_level0(self):
        # given
        sut = go2.PathStorage(empty_stub())

        # when
        sut.add(self.path, 0)

        # then
        self.assertIn(self.path, sut.group[0])

    def test_add_level0_ignore_repeat(self):
        # given
        sut = go2.PathStorage(empty_stub())

        # when
        sut.add(self.path, 0)
        sut.add(self.path, 0)

        # then
        self.assertEquals(len(sut.group[0]), 1)

    def test_add_level0_goes_to_menu(self):
        # given
        menu = empty_mock()
        expect_call(menu.add_entry)

        sut = go2.PathStorage(menu)

        # when
        sut.add(self.path, 0)

        # then
        menu.assert_that_is_satisfied()

    def test_add_level_not0_does_not_go_to_menu(self):
        # given
        menu = empty_mock()
        sut = go2.PathStorage(menu)

        # when
        sut.add(self.path, 1)

        # then
        menu.assert_that_is_satisfied()

    def test_add_alternate(self):
        # given
        menu = empty_mock()
        expect_call(menu.add_separator)
        expect_call(menu.add_entry).with_args(self.path)
        sut = go2.PathStorage(menu)

        # when
        sut.add(self.path, 1)
        sut.flush_alternate()

        # then
        menu.assert_that_is_satisfied()

    def test_add_filtered(self):
        # given
        menu = empty_mock()
        sut = go2.PathStorage(menu)
        sut.add_filter(foo_filter)

        # when
        sut.add('foo', 0)

        # then
        menu.assert_that_is_satisfied()


class Test_Menu(unittest.TestCase):
    pass

# providers -> queue -> QueueReactor -> PathStorage.add   -> menu.add_entry
#                                       PathStorage.flush -> menu.add_entry
#              key   ->      Reactor ->                   -> menu.keypress


class Test_Menu(unittest.TestCase):
    def FIXME_test_choice(self):
        # given
        queue = mp.Queue()
        reactor = QueueReactor()
        menu = go2.Menu(reactor)

        path_storage = go2.PathStorage(menu)
        path_storage.add_filter(foo_filter)

        reactor.io_add_watch(menu.fd, menu.keypressed)
        reactor.queue_add_watch(queue,
                                go2.QueueExtractor(queue, path_storage.add))
        reactor.run()

        path_storage.flush_alternate()
