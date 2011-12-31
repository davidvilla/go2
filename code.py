#!/usr/bin/python
# -*- coding:utf-8; tab-width:4; mode:python -*-


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



ui = UI()
path_list = PathList(ui.add_entry)

queue = mp.Queue()

r = QueueReactor()
r.add_queue_watch(queue, ob.notify)
r.add_io_watch(stdin, ui.on_key_pressed)
r.run()
