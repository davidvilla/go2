go2
===

- PYPI: https://pypi.org/project/go2/
- Debian package: https://uclm-arco.github.io/debian/

Description
-----------

go2 provides an easy method to change among directories by a fast way. go2 is a console
program similar to the old PCTools dm or the ncd from Norton, although this is designed
for bash.

Features:

- cache of recent searches;
- history list of visited directories;
- blacklist of directories not to search;
- configuration file for default options;
- multithreaded execution.

Similar programs
----------------

- wcd
- kcd
- cdargs
- apparix
- autojump

Instalation
-----------

The easiest way is to install the debian package (also available in Ubuntu) using
apt-get::

    # apt-get install go2

Once it is installed, each user need to include next line at the end of their ~/.bashrc:
[ -e /usr/lib/go2/go2.sh ] && source /usr/lib/go2/go2.sh In the next shell session, go2
will be ready to use.


Manual
------

Go2 is very easy to use. From any directory just execute::

    $ go2 prefix

when 'prefix' is the beginning of the directory you want to go. go2 will search in your
'home' and it will list all the directories that match the prefix.

Each match has a associated letter. To choose the target, just press the corresponding
key. If you want to abort the search, you may press the ESC key (or C-c). You may choose
the first match pressing ENTER. The selection may occurs in any moment, it is not required
that you wait the searching is finished.

go2 remembers all the successful searches, so it is faster each time.

Other options
-------------

go2 has some options to perform searches from the '/' directory, to ask case-insensitive
matching, etc. Try this::

    $ go2 --help
    usage: go2 [-h] [--cd] [-i] [-r] [--setup] [--version] [pattern [pattern ...]]

    go2 is a fast directory finder.

    This is version 1.20111128, Copyright (C) 2004-2011 David Villa Alises.
    go2 comes with ABSOLUTELY NO WARRANTY; This is free software, and you
    are welcome to redistribute it under certain conditions; See COPYING
    for details.

    positional arguments:
      pattern            pattern to find

    optional arguments:
      -h, --help         show this help message and exit
      --cd               change to given dir and add it to the cache (useful as
                         'cd' alias)
      -i, --ignore-case  ignore case search
      -r, --from-root    search in whole file system
      --setup            install go2 in your .bashrc
      --version          show program's version number and exit


'pattern' may be a word list so it is possible to do things like::

    $ go2 -r cach arch
    a: /var/cache/apt/archives
    Searching...


.. Local Variables:
..  coding: utf-8
..  mode: flyspell
..  ispell-local-dictionary: "american"
.. End:
