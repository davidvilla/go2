#!/usr/bin/python3
# -*- coding:utf-8; tab-width:4; mode:python -*-

# It contains code chunks from python-filesystem (fs.osfs module)

import sys
import os
import errno
from functools import wraps


ERR_PATH_EXISTS_AS_FILE = \
    "Cannot create directory, there's already a file of that name."

ERR_DIR_ALREADY_EXISTS = \
    "Can not create a directory that already exists."


class FSError(Exception):
    pass


class ResourceNotFoundError(FSError):
    pass


class ResourceInvalidError(FSError):
    pass


class DestinationExistsError(FSError):
    pass


class ParentDirectoryMissingError(FSError):
    pass


def convert_os_errors(func):
    opname = func.__name__

    @wraps(func)
    def wrapper(self, *args, **kwds):
        try:
            return func(self, *args, **kwds)
        except (OSError, IOError) as e:
            (exc_type, exc_inst, tb) = sys.exc_info()
            path = getattr(e, "filename", None)

#            if path and path[0] == "/" and hasattr(self, "root_path"):
#                path = normpath(path)
#                if isprefix(self.root_path,path):
#                    path = path[len(self.root_path):]

#            if not hasattr(e,"errno") or not e.errno:
#                raise OperationFailedError(opname,details=e),None,tb

            if e.errno == errno.ENOENT:
                raise ResourceNotFoundError(path, opname=opname, details=e)
            if e.errno == errno.ESRCH:
                raise ResourceNotFoundError(path, opname=opname, details=e)
#            if e.errno == errno.ENOTEMPTY:
#                raise DirectoryNotEmptyError(path, opname=opname, details=e), None, tb
            if e.errno == errno.EEXIST:
                raise DestinationExistsError(path, opname=opname, details=e)
            if e.errno == 183:  # some sort of win32 equivalent to EEXIST
                raise DestinationExistsError(path, opname=opname, details=e)
            if e.errno == errno.ENOTDIR:
                raise ResourceInvalidError(path, opname=opname, details=e)
            if e.errno == errno.EISDIR:
                raise ResourceInvalidError(path, opname=opname, details=e)
            if e.errno == errno.EINVAL:
                raise ResourceInvalidError(path, opname=opname, details=e)
#            if e.errno == errno.EOPNOTSUPP:
#                raise UnsupportedError(opname, details=e), None, tb

#            if e.errno == errno.ENOSPC:
#                raise StorageSpaceError(opname,details=e),None,tb

#            if e.errno == errno.EPERM:
#                raise PermissionDeniedError(opname,details=e),None,tb

#            if e.errno == errno.EACCES:
#                if sys.platform == "win32":
#                    if e.args[0] and e.args[0] == 32:
#                        raise ResourceLockedError(path,opname=opname,details=e),None,tb
#                raise PermissionDeniedError(opname,details=e),None,tb
#            # Sometimes windows gives some random errors...
#            if sys.platform == "win32":
#                if e.errno in (13,):
#                    raise ResourceInvalidError(path,opname=opname,details=e),None,tb

#            raise OperationFailedError(opname,details=e),None,tb
    return wrapper


class OSFS(object):
    def __init__(self, root):
        self.root = root

    def makedir(self, path, recursive=False, allow_recreate=False):
        try:
            if recursive:
                os.makedirs(path)
            else:
                os.mkdir(path)
        except OSError as e:
            if e.errno in [errno.EEXIST, 183]:
                if self.isfile(path):
                    raise ResourceInvalidError(
                        path, msg=ERR_PATH_EXISTS_AS_FILE)
                if not allow_recreate:
                    raise DestinationExistsError(
                        path, msg=ERR_PATH_EXISTS_AS_FILE)
                return

            if e.errno == errno.ENOENT:
                raise ParentDirectoryMissingError(path)

            raise

    def getcontents(self, fpath):
        try:
            with open(fpath) as fd:
                return fd.read()
        except IOError:
            raise ResourceNotFoundError(fpath)

    def setcontents(self, fpath, contents):
        try:
            with open(fpath, 'w') as fd:
                fd.write(contents)
        except IOError:
            raise ResourceNotFoundError(fpath)

    def open(self, fpath, mode='r'):
        try:
            return open(fpath, mode)
        except IOError:
            raise ResourceNotFoundError

    def exists(self, fpath):
        return os.path.exists(fpath)

    def isfile(self, fpath):
        return os.path.isfile(fpath)

    def isdir(self, path):
        return os.path.isdir(path)
