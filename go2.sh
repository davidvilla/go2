#!/bin/bash --
GO2TMP=~/.go2/tmp
function go2 {
    clear
    /usr/lib/go2/go2.py $*;
    if [ -e $GO2TMP ]; then
	cd "$(cat $GO2TMP)"
	rm $GO2TMP > /dev/null
    fi
}
