===
go2
===

----------------
directory finder
----------------

:Author: David.Villa@uclm.es
:date:   2011-08-05
:Manual section: 1

SYNOPSIS
========

``go2`` [-h] [--cd] [-i] [-r] [--setup] [--version] [pattern [pattern ...]]

DESCRIPTION
===========

This manual page documents briefly the ``go2`` command.

This manual page was written for the Debian(TM) distribution because
the original program does not have a manual page.

``go2`` is a program that finds (and changes to) directories.

IMPORTANT
=========

``go2`` requires be loaded from the shell. To do this include the next
sentence in your $HOME/.bashrc file:

|
|    [ -e /usr/lib/go2/go2.sh ] && source /usr/lib/go2/go2.sh

If your wish improve directory caching, you may include also the next
sentence:

|
|  alias cd='go2 --cd'

Both are made by the setup process the first time you invoke ``go2``.

OPTIONS
=======

This program follows the usual GNU command line syntax, with long
options starting with two dashes ('-'). A summary of options is
included below. For a complete description, see the Info files.

--cd=PATH	Just change working directory

-i		Case insensitive.

-r		Search from root directory.

-d		Search in hidden directories.

-l		List only, print matches and exists.

--setup		Install go2 in your .bashrc.

SEE ALSO
========

| This program is fully documented in
| http://arco.esi.uclm.es/~david.villa/go2.html


COPYRIGHT
=========

Copyright © 2011 David Villa

This manual page was written for the Debian system (and may be used by
others).

Permission is granted to copy, distribute and/or modify this document
under the terms of the GNU General Public License, Version 2 or (at
your option) any later version published by the Free Software
Foundation.

On Debian systems, the complete text of the GNU General Public License
can be found in /usr/share/common-licenses/GPL.

.. Local Variables:
..  coding: utf-8
..  mode: flyspell
..  ispell-local-dictionary: "american"
.. End:
