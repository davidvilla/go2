#!/usr/bin/atheist
# -*- mode:python; coding:utf-8 -*-

import sys
import os
import time

import unittest2 as unittest
from fs.memoryfs import MemoryFS
from pyDoubles.framework import *

import go2


def hello_task(output):
    output.put("hi")

def sleep(output, t):
    time.sleep(t)

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

    def test_add_task_sleep(self):
        self.pool.add_task(sleep, 1)
        self.pool.join()
