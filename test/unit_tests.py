#!/usr/bin/atheist
# -*- mode:python; coding:utf-8 -*-

import sys
import os
import time
import multiprocessing as mp

from unittest import TestCase

import fs
from fs.memoryfs import MemoryFS
from fs import ResourceNotFoundError

from hamcrest import anything
from doublex import Stub, Spy, Mock, ANY_ARG, assert_that, called, verify
import gobject

import go2


HOME = '/home/user'


def hello_task():
    return ["hi"]


def foo_filter(value):
    return value == 'foo'


class StubFS(object):
    def setUp(self):
        self.fs = MemoryFS()
        self.mkdir('lab')

        config = go2.get_config([])
        config.fs = self.fs
        go2.config = config

    def mkdir(self, relpath):
        self.fs.makedir(fs.join(HOME, relpath), recursive=True)


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

        with Mock() as handler:
            handler.handle(anything(), gobject.IO_IN, queue).returns(False)

        self.sut.queue_add_watch(queue, handler.handle)

        # when
        self.sut.process_pending()

        # then
        assert_that(handler, verify())

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
        sut = go2.PathBuffer(Stub())

        # when
        sut.add(go2.PathItem(self.path, 0))

        # then
        self.assertIn(self.path, sut.groups[0])

    def test_add_level0_ignore_repeat(self):
        # given
        sut = go2.PathBuffer(Stub())

        # when
        sut.add(go2.PathItem(self.path, 0))
        sut.add(go2.PathItem(self.path, 0))

        # then
        self.assertEquals(len(sut.groups[0]), 1)

    def test_add_level0_goes_to_menu(self):
        # given
        with Mock() as menu:
            menu.add_entry(ANY_ARG)

        sut = go2.PathBuffer(menu)

        # when
        sut.add(go2.PathItem(self.path, 0))

        # then
        assert_that(menu, verify())

    def test_add_level_not0_does_not_go_to_menu(self):
        # given
        menu = Mock()
        sut = go2.PathBuffer(menu)

        # when
        sut.add(go2.PathItem(self.path, 1))

        # then
        assert_that(menu, verify())

    def test_add_alternate(self):
        # given
        with Mock() as menu:
            menu.next_group()
            menu.add_entry(self.path)

        sut = go2.PathBuffer(menu)

        # when
        sut.add(go2.PathItem(self.path, 1))
        sut.flush_alternate()

        # then
        assert_that(menu, verify())

    def test_add_filtered(self):
        # given
        menu = Mock()
        sut = go2.PathBuffer(menu)
        sut.add_filter(foo_filter)

        # when
        sut.add(go2.PathItem('foo', 0))

        # then
        assert_that(menu, verify())


class PathFileHelper(StubFS):
    def PathFileStore_with_content(self, store, more=''):
        self.fs.createfile(store, u'''\
1: /home/user/lab
2: /home/user/lab/media
''' + more)
        return go2.PathFileStore(store)


class Test_PathFileStore(TestCase, PathFileHelper):
    def setUp(self):
        StubFS.setUp(self)
        self.store_fpath = '/paths'

    def assert_visits(self, store_path, path, visits):
        self.assertIn("{0}:{1}\n".format(visits, path),
                      self.fs.getcontents(self.store_fpath))

    def store_create_and_insert(self, store_path, path, size=None, visits=None):
        sut = self.PathFileStore_with_content(store_path)
        sut.add_visit(path).save()
        if size:
            self.assertEquals(len(sut.data), size)
        if visits:
            self.assert_visits(store_path, path, visits)
        return sut

    def test_load_ok(self):
        sut = self.PathFileStore_with_content(store=self.store_fpath)
        self.assertItemsEqual(
            sut.data.keys(),
            [u'/home/user/lab', u'/home/user/lab/media'])

    def test_load_missing(self):
        with self.assertRaises(ResourceNotFoundError):
            go2.PathFileStore('missing')

    def test_insert_new(self):
        self.store_create_and_insert(self.store_fpath, u'/XXX', 3, 1)

    def test_insert_old_most_visited(self):
        path = u'/home/user/lab/media'
        sut = self.store_create_and_insert(
            self.store_fpath, path, size=2, visits=3)
        self.assertEquals(list(sut)[0], path)

    def test_insert_old_less_visited(self):
        path = u'/home/user/lab'
        sut = self.store_create_and_insert(
            self.store_fpath, path, size=2, visits=2)
        sut.add_visit(path).save()
        self.assert_visits(self.store_fpath, path, 3)
        self.assertEquals(list(sut)[0], path)

    def test_deprecated_file_format(self):
        # given
        self.fs.createfile(self.store_fpath, u'''\
/home/user/lab
/home/user/lab/media
''')
        # when
        go2.PathFileStore(self.store_fpath).save()

        # then
        self.assertItemsEqual(
            self.fs.getcontents(self.store_fpath).split(),
            u'''\
1:/home/user/lab
1:/home/user/lab/media
'''.split())

    def test_wrong_file_encoding_lines_are_pruned(self):
        self.skipTest("not pruned")

        # given
        go2.config.encoding = 'utf-8'
        self.fs.createfile(self.store_fpath, u'''\
1:/foo
1:/home/ñandú
'''.encode('latin1'))

        # when
        go2.PathFileStore(self.store_fpath).save()

        # then
        self.assertEquals(
            self.fs.getcontents(self.store_fpath).strip(),
            "1:/foo")


class Test_from_file_provider(TestCase, PathFileHelper):
    def setUp(self):
        StubFS.setUp(self)

    def test_search_existing(self):
        # given
        go2.config.matcher = go2.PathMatcher(['la'])
        store = self.PathFileStore_with_content('paths')

        # whem
        paths = list(go2.from_file_provider(store))

        # then
        self.assertIn(go2.PathItem(u'/home/user/lab'), paths)

    def test_search_missing(self):
        "from_file_provider remove checked missing paths"
        sut = self.PathFileStore_with_content('paths')
        go2.config.pattern = ['med']

        paths = list(go2.from_file_provider(sut))

        self.assertFalse(paths)


class Test_Menu(TestCase):
    def setUp(self):
        self.reactor_spy = Spy()
        self.fd_stub = Stub()

    def new_menu(self, **kargs):
        params = dict(reactor=self.reactor_spy, out=self.fd_stub)
        params.update(kargs)
        return go2.Menu(**params)

    def test_add_entry(self):
        sut = self.new_menu()

        sut.add_entry('foo')

        self.assertIn('foo', sut.entries)

    def test_FullSinkException(self):
        # given
        sut = self.new_menu(max_size=1)

        # when/then
        sut.add_entry('foo')
        with self.assertRaises(go2.Menu.FullSinkException):
            sut.add_entry('bar')

        self.assert_(sut.is_full)

    def test_print_ENTER_for_first(self):
        # given
        fd = Spy()
        sut = self.new_menu(out=fd)

        # when
        sut.add_entry('foo')

        # then
        assert_that(fd.write, called().with_args('a: foo'))

    def test_print_second(self):
         # given
        fd = Spy()
        sut = self.new_menu(out=fd)

        # when
        sut.add_entry('foo')
        sut.add_entry('bar')

        # then
        assert_that(fd.write, called())
        assert_that(fd.write, called().with_args('b: bar'))

    def test_select_first_with_empty_menu(self):
        # given
        sut = self.new_menu()

        # when/then
        with self.assertRaises(go2.Sink.InvalidChoiceException):
            sut.perform_choice(0)

    def test_valid_key(self):
        # given
        sut = self.new_menu()
        sut.add_entry('foo')

        # when
        sut.perform_choice(0)

        # then
        self.assertEquals(sut.target, 'foo')
        assert_that(self.reactor_spy.quit, called())

    def test_wrong_key_raises_invalid(self):
        # given
        sut = self.new_menu()
        sut.add_entry('foo')

        # when/then
        with self.assertRaises(go2.Sink.InvalidChoiceException):
            sut.perform_choice(1)

    def FIXME_test_groups(self):
        pass


class Test_UserChoiceHanlder(TestCase):
    def input_stub(self, key):
        with Stub() as retval:
            retval.read(anything()).returns(key)

        return retval

    def test_ESC_quit_reactor(self):
       # given
        sut = go2.UserInputHandler()
        fd = self.input_stub(chr(go2.ESC))

        # when/then
        with self.assertRaises(go2.CancelException):
            sut(fd)

        # then
#        assert_that_was_called(self.reactor_spy.quit)


class TestExcludeFilter(TestCase):
    def create_filter(self, *dirs):
        return go2.exclude_filter(list(dirs))

    def test_excluded_path_with_1_pattern(self):
        sut = self.create_filter("foo")

        self.assert_(
            sut("/home/user/repo/foo"))

    def test_excluded_path_with_2_patterns(self):
        # given
        sut = self.create_filter("foo", "bar")

        self.assert_(sut("/home/foo"))
        self.assert_(sut("/home/bar"))

    def test_not_matching_path(self):
        sut = self.create_filter("foo")

        self.assertFalse(
            sut('/usr/share'))

    def test_path_match_in_any_place(self):
        sut = self.create_filter("foo")

        self.assert_(
            sut('/usr/foo/share'))

    def test_path_not_match_if_not_full_name(self):
        sut = self.create_filter("foo")

        self.assertFalse(
            sut('/usr/xxfoo'))

        self.assertFalse(
            sut('/usr/fooxx'))

    def test_absolute_dir(self):
        sut = self.create_filter('/usr/local/*')

        self.assert_(sut('/usr/local/foo'))
        self.assert_(sut('/usr/local'))
