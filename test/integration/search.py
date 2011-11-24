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
    def test_choice_first_entry_with_previous_ignored(self):
        # given
        queue = mp.Queue()
        read_end, write_end = pipe()
        out = empty_spy()

        reactor = go2.QueueReactor()
        menu = go2.Menu(reactor, out)

        path_storage = go2.PathStorage(menu)
        path_storage.add_filter(foo_filter)

        reactor.queue_add_watch(queue, go2.QueueExtractor(path_storage.add))
        reactor.io_add_watch(read_end, menu.input_handler)

        # when
        queue.put(('foo', 0))
        queue.put(('bar', 0))
        write_end.write('a')
        reactor.run()

        # then
        self.assertEquals(path_storage.group[0], ['bar'])
        self.assertEquals(menu.entries, ['bar'])
        assert_that_was_called(out.write).with_args('a: bar [ENTER]')
        self.assertEquals(menu.choice, 0)

#    def test_threaded(self):
#        # given
#        queue = mp.Queue()
#        out = empty_spy()
#        menu = go2.Menu(out)
#        path_storage = go2.PathStorage(menu)
#        read_end, write_end = pipe()
#
#        queue_reader = go2.QueueReaderThread(queue, path_storage.add)
#        key_reader = go2.KeyReaderThread(read_end, menu.input_handler)
#
#        # when
#        queue_reader.start()
#        key_reader.start()
#
#        queue.put(('foo', 0))
#        queue.put(('bar', 0))
#        write_end.write('a')
#
#        key_reader.join()
#        queue_reader.quit()
#
#        # then



# given: un pool con tareas
# when:  el pool queda ocioso
# then:  el reactor acaba

# given: menu con una sola entrada
# when:  todas las tareas han terminado
# then:  elegir la única entrada sin preguntar

# given: un reactor
# when:  el reactor acaba
# then:  enviar las rutas alternativas al menú

# given: un reactor y un menú
# when:  el menú se llena
# then:  el reactor acaba


# condiciones de fin
# - ESC o CTRL-C                      - CancelException
# - Ninguna coincidencia
# - Solo una coincidencia
# - Elegir entre varias coincidencias
# - Menu lleno, elegir
