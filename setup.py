#!/usr/bin/python

from distutils.core import setup

setup(name         = 'go2',
      version      = '0.0.2',
      description  = 'go2 directory finder',
      author       = 'David Villa Alises',
      author_email = 'david.villa@uclm.es>',
      url          = 'http://arco.inf-cr.uclm.es/~dvilla/go2.html',
      license      = 'GPL v2 or later',
      data_files   = [('/usr/lib/go2', ['go2.sh']),
                      ('/usr/share/man/man1', ['go2.1'])],
      scripts      = ['go2.py'],
      )
