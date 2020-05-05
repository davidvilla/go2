#!/usr/bin/make -f
# -*- mode:makefile -*-

clean:
	find . -name *.pyc -delete
	find . -name *.pyo -delete
	find . -name *~ -delete
	$(RM) -r dist build
	$(RM) -r .svn debian MANIFEST
