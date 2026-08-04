#!/usr/bin/make -f

push:
	git push --tags

deb-update:
	ian build -cli

upload:
	$(RM) -r dist
	python3 setup.py sdist
	twine upload dist/*

clean:
	find . -name *.pyc -delete
	find . -name *.pyo -delete
	find . -name *~ -delete
	$(RM) -r dist build
	$(RM) -r .svn debian MANIFEST
