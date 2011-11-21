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


class FilteredObserver(object):
    def __init__(self, queue):
        self.observers = []
        self.filters = []

    def notify(self, item):
        if any(f(item) for f in self.filters):
            return

        for ob in self.observers:
            ob(item)

    def register(self, ob):
        self.observer.append(ob)

    def add_filter(self, f):
        self.filters.append(f)


ui = UI()
path_list = PathList(ui.add_entry)

ob = FilteredObserver()
ob.add_filter(is_ignored)
ob.register(path_list.add)

queue = mp.Queue()

r = QueueReactor()
r.add_queue_watch(queue, ob.notify)
r.add_io_watch(stdin, ui.on_key_pressed)
r.run()
