#!/usr/bin/atheist
# -*- mode:python; coding:utf-8 -*-

import sys
import os
import time
import multiprocessing as mp

from unittest2 import TestCase

from fs.memoryfs import MemoryFS
from fs import ResourceNotFoundError

from pyDoubles.framework import *
import gobject

import go2


def hello_task():
    return ["hi"]


def foo_filter(value):
    return value == 'foo'


class TestPool(TestCase):
    def setUp(self):
        self.pool = go2.ProcessPool()

    def test_create(self):
        self.pool.terminate()

    # Esta prueba no funciona con atheist
    def test_add_task_hello(self):
        self.pool.add_task(hello_task)

        self.assertEquals(self.pool.output_queue.get(timeout=1), "hi")

        self.pool.join()


class Test_QueueReactor(TestCase):
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

    def test_exception_break_reactor_and_re_raises_exception(self):
        def raise_exception():
            raise go2.CancelException()

        # given
        self.sut.timeout_add(1, raise_exception)

        # when/then
        with self.assertRaises(go2.CancelException):
            self.sut.run()


class Test_PathBuffer(TestCase):
    def setUp(self):
        self.path = '/usr/share'

    def test_add_level0(self):
        # given
        sut = go2.PathBuffer(empty_stub())

        # when
        sut.add(go2.PathItem(self.path, 0))

        # then
        self.assertIn(self.path, sut.groups[0])

    def test_add_level0_ignore_repeat(self):
        # given
        sut = go2.PathBuffer(empty_stub())

        # when
        sut.add(go2.PathItem(self.path, 0))
        sut.add(go2.PathItem(self.path, 0))

        # then
        self.assertEquals(len(sut.groups[0]), 1)

    def test_add_level0_goes_to_menu(self):
        # given
        menu = empty_mock()
        expect_call(menu.add_entry)

        sut = go2.PathBuffer(menu)

        # when
        sut.add(go2.PathItem(self.path, 0))

        # then
        menu.assert_that_is_satisfied()

    def test_add_level_not0_does_not_go_to_menu(self):
        # given
        menu = empty_mock()
        sut = go2.PathBuffer(menu)

        # when
        sut.add(go2.PathItem(self.path, 1))

        # then
        menu.assert_that_is_satisfied()

    def test_add_alternate(self):
        # given
        menu = empty_mock()
        expect_call(menu.add_separator)
        expect_call(menu.add_entry).with_args(self.path)
        sut = go2.PathBuffer(menu)

        # when
        sut.add(go2.PathItem(self.path, 1))
        sut.flush_alternate()

        # then
        menu.assert_that_is_satisfied()

    def test_add_filtered(self):
        # given
        menu = empty_mock()
        sut = go2.PathBuffer(menu)
        sut.add_filter(foo_filter)

        # when
        sut.add(go2.PathItem('foo', 0))

        # then
        menu.assert_that_is_satisfied()


class Test_Menu(TestCase):
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

    def test_FullMenuException(self):
        # given
        sut = self.new_menu(max_size=1)

        # when/then
        sut.add_entry('foo')
        with self.assertRaises(go2.Menu.FullMenuException):
            sut.add_entry('bar')

        self.assert_(sut.is_full)

    def test_print_ENTER_for_first(self):
        # given
        fd = empty_spy()
        sut = self.new_menu(out=fd)

        # when
        sut.add_entry('foo')

        # then
        assert_that_was_called(fd.write).with_args('a: foo')

    def test_print_second(self):
         # given
        fd = empty_spy()
        sut = self.new_menu(out=fd)

        # when
        sut.add_entry('foo')
        sut.add_entry('bar')

        # then
        assert_that_was_called(fd.write).with_args(ANY_ARG)
        assert_that_was_called(fd.write).with_args('b: bar')

    def test_select_first_with_empty_menu(self):
        # given
        sut = self.new_menu()
        fd = self.input_stub('a')

        # when
        sut.input_handler(fd)

        # then
        self.assertEquals(sut.target, None)

    def test_valid_key(self):
        # given
        sut = self.new_menu()
        sut.add_entry('foo')
        fd = self.input_stub('a')

        # when
        sut.input_handler(fd)

        # then
        self.assertEquals(sut.target, 'foo')
        assert_that_was_called(self.reactor_spy.quit)

    def test_wrong_key_is_ignored(self):
        # given
        sut = self.new_menu()
        sut.add_entry('foo')
        fd = self.input_stub('b')

        # when
        sut.input_handler(fd)

        # then
        self.assertEquals(sut.target, None)

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


class TestIgnore(TestCase):
    def create_manager(self, content):
        return go2.IgnoreManager(content)

    def test_ignored_path_with_1_pattern(self):
        sut = self.create_manager("foo")

        self.assert_(
            sut.is_ignored("/home/user/repo/foo"))

    def test_ignored_path_with_2_patterns(self):
        # given
        sut = self.create_manager('''
foo
bar''')

        # when
        foo = sut.is_ignored("/home/foo")
        bar = sut.is_ignored("/home/bar")

        # then
        self.assert_(foo and bar)

    def test_not_matching_path(self):
        sut = self.create_manager("foo")

        self.assertFalse(
            sut.is_ignored('/usr/share'))

    def test_path_match_in_any_place(self):
        sut = self.create_manager("foo")

        self.assert_(
            sut.is_ignored('/usr/foo/share'))

    def test_path_not_match_if_not_full_name(self):
        sut = self.create_manager("foo")

        self.assertFalse(
            sut.is_ignored('/usr/xxfoo'))

    def test_from_file__missing_file(self):
        # given
        fs = MemoryFS()
        config = go2.get_config()
        config.fs = fs
        go2.config = config

        # when
        with self.assertRaises(ResourceNotFoundError):
            go2.IgnoreManager.from_file('ignore')

    def test_from_file(self):
        # given
        fs = MemoryFS()
        fs.createfile('ignore', 'foo')
        config = go2.get_config()
        config.fs = fs
        go2.config = config

        # when
        sut = go2.IgnoreManager.from_file('ignore')

        # then
        self.assert_(sut.is_ignored('/home/foo'))
