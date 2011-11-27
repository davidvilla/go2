# -*- mode:python; coding:utf-8 -*-

import time
import multiprocessing as mp
import socket

import unittest2 as unittest
from pyDoubles.framework import empty_spy, assert_that_was_called

import go2


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

        self.reactor = go2.QueueReactor()
        self.menu = go2.Menu(self.reactor, self.out, max_size=menu_size)

        self.path_buffer = go2.PathBuffer(self.menu)

        self.reactor.queue_add_watch(
            self.queue,
            go2.QueueExtractor(self.path_buffer.add))
        self.reactor.io_add_watch(self.read_end, self.menu.input_handler)

    def test_choice_first_entry_with_previous_ignored(self):
        # given
        self.create_scenario()
        self.path_buffer.add_filter(foo_filter)

        # when
        self.queue.put(('foo', 0))
        self.queue.put(('bar', 0))
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

        # when
        self.queue.put(('foo', 0))
        self.queue.put(('bar', 0))
        self.reactor.process_pending()

        # then


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
