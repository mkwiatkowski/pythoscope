"""Definition of wrapperobject CPython's structure in ctypes. With this you can
get into wrapperobject internals without going to the C level.

See descrobject.c for reference:
  http://svn.python.org/view/python/trunk/Objects/descrobject.c?view=markup

Note that not all fields are defined, only those that I needed.
"""

from ctypes import c_long, py_object, cast, Structure, POINTER


ssize_t = c_long

class PyWrapperObject(Structure):
    _fields_ = [("ob_refcnt", ssize_t),
                ("ob_type", py_object),
                ("descr", py_object),
                ("self", py_object)]

def _wrapper_internals(wrapper):
    return cast(id(wrapper), POINTER(PyWrapperObject)).contents

def get_wrapper_self(wrapper):
    return _wrapper_internals(wrapper).self
