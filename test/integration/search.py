# -*- mode:python; coding:utf-8 -*-

import os
import time
import multiprocessing as mp
import socket

import unittest2 as unittest
from pyDoubles.framework import empty_spy, empty_stub, \
    when, assert_that_was_called

from go2 import PathItem, QueueReactor, QueueExtractor, PathBuffer, Menu, EndChecker


def foo_filter(value):
    return value == 'foo'

# providers -> queue.put -> QueueReactor -> PathStorage.add   -> menu.add_entry
#                                           PathStorage.flush -> menu.add_entry
#              key       ->      Reactor ->                   -> menu.input_handler


def pipe():
    a, b = socket.socketpair()
    read_end = a.makefile()
    write_end = b.makefile('w', 0)
    return read_end, write_end


class Test_Search(unittest.TestCase):
    def create_scenario(self, menu_size=26):
        self.queue = mp.Queue()
        self.read_end, self.write_end = pipe()
        self.out = empty_spy()

        self.reactor = QueueReactor()
        self.menu = Menu(self.reactor, self.out, max_size=menu_size)

        self.path_buffer = PathBuffer(self.menu)

        self.reactor.queue_add_watch(
            self.queue,
            QueueExtractor(self.path_buffer.add))

    def register_input(self):
        self.reactor.io_add_watch(self.read_end, self.menu.input_handler)

    def put(self, path):
        self.queue.put(PathItem(path))

    def test_choice_first_entry_with_previous_ignored(self):
        # given
        self.create_scenario()
        self.register_input()
        self.path_buffer.add_filter(foo_filter)

        # when
        self.put('foo')
        self.put('bar')
        self.write_end.write('a')
        self.reactor.run()

        # then
        self.assertEquals(self.path_buffer.groups[0], ['bar'])
        self.assertEquals(self.menu.entries, ['bar'])
        assert_that_was_called(self.out.write).with_args('a: bar')
        self.assertEquals(self.menu.target, 'bar')

    def test_full_menu(self):
        # given
        self.create_scenario(menu_size=1)
        self.register_input()

        # when
        self.put('foo')
        self.put('bar')
        self.reactor.process_pending()

        # then
        assert_that_was_called(self.out.write).with_args('a: foo')

    def atest_list_mode(self):
        def raw_formatter(index, path, suffix):
            return path + '\n'

        paths = ['foo', 'bar']

        # given
        pool = empty_stub()
        when(pool.has_tasks).then_return(False)

        self.create_scenario()
        self.reactor.timeout_add(250, EndChecker(
                pool, self.path_buffer, self.menu))
        self.menu.formatter = raw_formatter

        # when
        for i in paths:
            self.put(i)
        self.reactor.run()

        # then
        for i in paths:
            assert_that_was_called(self.out.write).with_args(i + '\n')

    def test_unicode(self):
        os.path.exists('ñandáéíóú')

# given: un pool con tareas
# when:  el pool queda ocioso
# then:  el menu espera una elección

# given: menu con una sola entrada
# when:  todas las tareas han terminado
# then:  elegir la única entrada sin preguntar

# given: un reactor
# when:  el reactor acaba
# then:  enviar las rutas alternativas al menú

# given: un reactor y un menú
# when:  el menú se llena
# then:  el menu espera una elección


# condiciones de fin
# - ESC o CTRL-C                      - CancelException
# - Ninguna coincidencia
# - Solo una coincidencia
# - Elegir entre varias coincidencias
# - Menu lleno, elegir
