/* Implementation of utility functions that couldn't be done in pure Python. */

#include <Python.h>
#include <compile.h>
#include <frameobject.h>

/* Python 2.3 headers don't include genobject (defined in Include/genobject.h
   in later versions). We only need to grab the gi_frame, so this definition
   will do. */
typedef struct {
    PyObject_HEAD
    PyFrameObject *gi_frame;
} genobject;

static PyObject *
_generator_has_ended(PyObject *self, PyObject *args)
{
    genobject *gen;
    PyFrameObject *frame;

    if (!PyArg_ParseTuple(args, "O", &gen))
        return NULL;
    /* Check if gen is a generator done on the Python level. */

    frame = gen->gi_frame;

    /* Python 2.5 releases gi_frame once the generator is done, so it has to be
       checked first.
       Earlier Pythons leave gi_frame intact, so the f_stacktop pointer
       determines whether the generator is still running. */
    return PyBool_FromLong(frame == NULL || frame->f_stacktop == NULL);
}

static PyMethodDef UtilMethods[] = {
    {"_generator_has_ended",  _generator_has_ended, METH_VARARGS, NULL},
    {NULL, NULL, 0, NULL}
};

PyMODINIT_FUNC
init_util(void)
{
    (void) Py_InitModule("_util", UtilMethods);
}
