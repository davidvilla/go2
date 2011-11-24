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

    def test_quit_on_conditiion(self):
        def quit(reactor):
            reactor.quit()

        # given
        gobject.timeout_add(1, quit, self.sut)

        # when
        self.sut.run()

        # then
        # reach this

    def test_exception_break_reactor(self):
        def raise_exception():
            raise go2.CancelException()

        # given
        self.sut.timeout_add(1, raise_exception)

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


# class Test_quit_handler(unittest.TestCase):
#     def test_any_key(self):
#         # given
#         reactor = empty_mock()
#         expect_call(reactor.quit)
#         sut = go2.QuitHandler(reactor)
#
#         # when
#         sut(chr(go2.CTRL_C))
#
#         # then
#         reactor.assert_that_is_satisfied()


class Test_Menu(unittest.TestCase):
    def setUp(self):
        self.reactor_spy = empty_spy()
        self.fd_stub = empty_stub()

    def new_menu(self, **kargs):
        params = dict(reactor=self.reactor_spy, out=self.fd_stub)
        params.update(kargs)
        return go2.Menu(**params)

    def input_stub(self, key):
        retval = empty_stub()
        when(retval.read).then_return(key)
        return retval

    def test_add_entry(self):
        sut = self.new_menu()

        sut.add_entry('foo')

        self.assertIn('foo', sut.entries)

    def test_FullException(self):
        # given
        sut = self.new_menu(max_size=1)

        # when/then
        sut.add_entry('foo')
        with self.assertRaises(go2.Menu.FullException):
            sut.add_entry('bar')

        self.assert_(sut.is_full())

    def test_print_ENTER_for_first(self):
        # given
        fd = empty_mock()
        expect_call(fd.write).with_args('a: foo [ENTER]')
        sut = self.new_menu(out=fd)

        # when
        sut.add_entry('foo')

        # then
        fd.assert_that_is_satisfied()

    def test_print_second(self):
         # given
        fd = empty_mock()
        expect_call(fd.write).with_args(ANY_ARG)
        expect_call(fd.write).with_args('b: bar')
        sut = self.new_menu(out=fd)

        # when
        sut.add_entry('foo')
        sut.add_entry('bar')

        # then
        fd.assert_that_is_satisfied()

    def test_valid_key(self):
        # given
        sut = self.new_menu()
        sut.add_entry('foo')
        fd = self.input_stub('a')

        # when
        sut.input_handler(fd)

        # then
        self.assertEquals(sut.choice, 0)
        assert_that_was_called(self.reactor_spy.quit)

    def test_wrong_key_is_ignored(self):
        # given
        sut = self.new_menu()
        sut.add_entry('foo')
        fd = self.input_stub('b')

        # when
        sut.input_handler(fd)

        # then
        self.assertEquals(sut.choice, None)

    def test_ESC_quit_reactor(self):
       # given
        sut = self.new_menu()
        fd = self.input_stub(chr(go2.ESC))

        # when/then
        with self.assertRaises(go2.CancelException):
            sut.input_handler(fd)

        # then
#        assert_that_was_called(self.reactor_spy.quit)

    def FIXME_test_separators(self):
        pass
