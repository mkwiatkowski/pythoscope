from pythoscope.inspector.dynamic import inspect_code_in_context
from pythoscope.execution import Execution
from pythoscope.store import Class, Function, Method, Project
from pythoscope.util import last_exception_as_string, last_traceback

from assertions import *

__all__ = ["inspect_returning_callables", "inspect_returning_execution",
    "inspect_returning_callables_and_execution",
    "inspect_returning_single_callable", "inspect_returning_single_call"]


class ClassMock(Class):
    """Class that has all the methods you try to find inside it via
    find_method_by_name().
    """
    def __init__(self, name):
        Class.__init__(self, name)
        self._methods = {}

    def find_method_by_name(self, name):
        if not self._methods.has_key(name):
            self._methods[name] = Method(name)
        return self._methods[name]

class ProjectMock(Project):
    """Project that has all the classes, functions and generators you try to
    find inside it via find_object().
    """
    ignored_modules = ["__builtin__", "exceptions"]

    def __init__(self, ignored_functions=[]):
        self.ignored_functions = ignored_functions
        self.path = "."
        self._classes = {}
        self._functions = {}

    def find_object(self, type, name, modulepath):
        if modulepath in self.ignored_modules:
            return None
        if type is Function and name in self.ignored_functions:
            return None

        object_id = (name, modulepath)
        container = self._get_container_for(type)

        if not container.has_key(object_id):
            container[object_id] = self._create_object(type, name)
        return container[object_id]

    def iter_callables(self):
        for klass in self._classes.values():
            for user_object in klass.user_objects:
                yield user_object
        for function in self._functions.values():
            yield function

    def get_callables(self):
        return list(self.iter_callables())

    def _get_container_for(self, type):
        if type is Class:
            return self._classes
        elif type is Function:
            return self._functions
        else:
            raise TypeError("Cannot store %r inside a module." % type)

    def _create_object(self, type, name):
        if type is Class:
            return ClassMock(name)
        else:
            return type(name)

def inspect_returning_callables_and_execution(fun, ignored_functions=None):
    project = ProjectMock(ignored_functions or [])
    execution = Execution(project=project)

    try:
        inspect_code_in_context(fun, execution)
    # Don't allow any POEs exceptions to propagate to the testing code.
    # Catch both string and normal exceptions.
    except:
        print "Caught exception inside point of entry:", last_exception_as_string()
        print last_traceback()

    return project.get_callables(), execution

def inspect_returning_callables(fun, ignored_functions=None):
    return inspect_returning_callables_and_execution(fun, ignored_functions)[0]

def inspect_returning_execution(fun):
    return inspect_returning_callables_and_execution(fun, None)[1]

def inspect_returning_single_callable(fun):
    callables = inspect_returning_callables(fun)
    return assert_one_element_and_return(callables)

def inspect_returning_single_call(fun):
    callables = inspect_returning_callables(fun)
    callable = assert_one_element_and_return(callables)
    return assert_one_element_and_return(callable.calls)

