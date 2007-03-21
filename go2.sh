#!/bin/bash
GO2TMP=~/.go2/tmp
function go2 {
    go2cmd $*;
    if [ -e $GO2TMP ]; then
	    cd "`cat $GO2TMP`"
	    rm $GO2TMP > /dev/null
    fi
}
