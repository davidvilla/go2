#!/usr/bin/atheist
# -*- mode:python; coding:utf-8 -*-

import sys
import os

import unittest2 as unittest
from fs.memoryfs import MemoryFS
from pyDoubles.framework import *

sys.path.append('$basedir')

import go2
from go2 import MatchLevel as Level


class Test_match(unittest.TestCase):
#    def setUp(self):
#        self.config = go2.get_config([])
#        go2.config = self.config

    def assert_match(self, pattern, result, paths):
        matcher = go2.PathMatcher(pattern)
        for p in paths:
            self.assertEquals(matcher.match(p), result)

    def test_single(self):
        self.assert_match(
            ['foo'], Level.START,
            ['/foo',
             '/buzz/foobar',
             '/foo/bar/foofoo',
             ])

    def test_single_i18n(self):
        self.assert_match(
            [u'ñandú'], Level.START,
            [u'/ñandú',
             u'/buzz/ñandúmar',
             ])

    def test_single_negative(self):
        self.assert_match(
            ['foo'], Level.NO_MATCH,
            ['/foa',
             '/buzz/foo/bar',
             '/foo/bar/but',
             ])

    def test_single_ignorecase(self):
        self.assert_match(
            ['foo'], Level.START_IGNORECASE,
            ['/Foo',
             '/buzz/fOo',
             '/foo/bar/FOO',
             ])

    def disable_test_single_ignorecase_i18n(self):
        self.assert_match(
            ['ñandú'], Level.START_IGNORECASE,
            ['/Ñandúfoo',
             '/ñandÚbar',
             '/buzz/ñandúmar',
            ])

    def test_single_contain(self):
        self.assert_match(
            ['foo'], Level.CONTAIN,
            ['/bafoo',
             '/buzz/tafoobar',
             '/foo/bar/fofoofoOO',
             ])

    def test_single_contain_insensitve(self):
        self.assert_match(
            ['FOO'], Level.CONTAIN_IGNORECASE,
            ['/bafoo',
             '/buzz/tafOobar',
             '/foo/bar/fofoofOO',
             ])


    def test_multi(self):
        self.assert_match(
            ['usr', 'loc'], Level.START,
            ['/usr/share/local',
             '/mnt/usr-doc/lib/loc',
             ])

    def test_multi_negative(self):
        self.assert_match(
            ['usr', 'loc'], Level.NO_MATCH,
            ['/usr/share/aloal',
             '/bin/local',
             '/usr/share/doc',
             ])

    def test_multi_ignorecase(self):
        self.assert_match(
            ['usr', 'loc'], Level.START_IGNORECASE,
            ['/usr/share/LOCAL',
#             '/mnt/Usr-doc/lib/loc',
             ])

    def test_multi_contain(self):
        self.assert_match(
            ['sr', 'oca'], Level.CONTAIN,
            ['/usr/share/local',
             '/mnt/usr-doc/lib/local',
             ])


class Test_high_pattern(unittest.TestCase):
    def setUp(self):
        self.config = go2.get_config([])
        self.config.before = '['
        self.config.after = ']'
        go2.config = self.config

    def test_single(self):
        matcher = go2.PathMatcher(['sto'])
        self.assertEquals(matcher.high_pattern('/usr/local/stow'),
                          '/usr/local/[sto]w')

        self.assertEquals(matcher.high_pattern('/usr/local/stow-1/stow-2'),
                          '/usr/local/stow-1/[sto]w-2')

    def test_single_ignorecase(self):
        matcher = go2.PathMatcher(['STO'])
        self.assertEquals(matcher.high_pattern('/usr/mostow/local/stow'),
                          '/usr/mostow/local/[sto]w')

        matcher = go2.PathMatcher(['sto'])
        self.assertEquals(matcher.high_pattern('/usr/local/STOW'),
                          '/usr/local/[STO]W')

    def test_single_contains(self):
        matcher = go2.PathMatcher(['tow'])
        self.assertEquals(matcher.high_pattern('/usr/mostow/local/stow'),
                          '/usr/mostow/local/s[tow]')

    def test_multi(self):
        matcher = go2.PathMatcher(['shar', 'sto'])
        self.assertEquals(matcher.high_pattern('/usr/share/local/stow'),
                          '/usr/[shar]e/local/[sto]w')

    def test_multi_contains(self):
        matcher = go2.PathMatcher(['hare', 'tow'])
        self.assertEquals(matcher.high_pattern('/usr/shares/local/stows'),
                          '/usr/s[hare]s/local/s[tow]s')


UnitTestCase()
