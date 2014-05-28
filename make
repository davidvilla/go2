#!/usr/bin/make -f
# -*- mode:makefile -*-

URL_AUTH=svn+ssh://${ALIOTH_USER}@svn.debian.org/svn/python-apps/packages/go2/trunk
URL_ANON=svn://svn.debian.org/svn/python-apps/packages/go2/trunk

debian:
	@if [ ! -z "$${ALIOTH_USER}" ]; then \
	    svn co ${URL_AUTH} -N; \
	else \
            echo anon svn; \
	    svn co ${URL_ANON} -N; \
	fi

	mv trunk/.svn .
	rmdir trunk
	svn up debian

clean:
	find . -name *.pyc -delete
	find . -name *.pyo -delete
	find . -name *~ -delete
	$(RM) -r dist build
	$(RM) -r .svn debian MANIFEST
