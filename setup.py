#!/usr/bin/env python3

# Copyright (C) 2004-2020 David Villa Alises
#
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import os
from setuptools import setup

def local_open(fname):
    return open(os.path.join(os.path.dirname(__file__), fname))


with open("README.md", "r") as readme:
    long_description = readme.read()

exec(open('version.py').read())


setup(name         = 'go2',
      version      = __version__,
      description  = 'go2 directory finder',
      author       = 'David Villa Alises',
      author_email = 'David.Villa@gmail.com',
      url          = 'https://bitbucket.org/DavidVilla/go2',
      license      = 'GPL v2 or later',
      data_files   = [('lib/go2', ['go2.sh', 'go2.py', 'osfs.py']),
                      ('share/man/man1', ['go2.1'])],
      scripts      =  ['go2'],
      long_description=long_description,
      long_description_content_type="text/markdown",
      classifiers=[
        "Programming Language :: Python :: 3",
      ]
      )
