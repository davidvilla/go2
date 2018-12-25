#!/usr/bin/python

from distutils.core import setup

setup(name         = 'go2',
      version      = '2.20170703',
      description  = 'go2 directory finder',
      author       = 'David Villa Alises',
      author_email = 'David.Villa@gmail.com',
      url          = 'http://savannah.nongnu.org/projects/go2/',
      license      = 'GPL v2 or later',
      data_files   = [('/usr/lib/go2', ['go2.sh', 'go2.py', 'osfs.py']),
                      ('/usr/share/man/man1', ['go2.1']),
                      ('/usr/bin', ['go2'])],
      )
