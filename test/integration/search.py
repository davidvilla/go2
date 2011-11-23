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
    def test_choice(self):
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
