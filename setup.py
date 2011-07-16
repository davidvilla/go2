#!/usr/bin/python

from distutils.core import setup

version = file('debian/changelog').readline().split()[1][1:-1]

setup(name         = 'go2',
      version      = version,
      description  = 'go2 directory finder',
      author       = 'David Villa Alises',
      author_email = 'david.villa@uclm.es>',
      url          = 'http://arco.inf-cr.uclm.es/~dvilla/go2.html',
      license      = 'GPL v2 or later',
      data_files   = [('/usr/lib/go2', ['go2.sh', 'go2.py', 'go2.glade2']),
                      ('/usr/share/man/man1', ['go2.1']),
                      ('/usr/bin', ['go2'])],
      )
