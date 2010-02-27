from pythoscope.compat import set
from pythoscope.util import union


class CodeString(str):
    """A string that holds information on the piece of code (like a function
    or method call it) it represents.

    `uncomplete` attribute denotes whether it is a complete, runnable code
    or just a template.

    `imports` is a list of imports that this piece of code requires.
    """
    def __new__(cls, string, uncomplete=False, imports=None):
        if imports is None:
            imports = set()
        code_string = str.__new__(cls, string)
        code_string.uncomplete = uncomplete
        code_string.imports = imports
        return code_string

    def extend(self, value, uncomplete=False, imports=set()):
        return CodeString(value, self.uncomplete or uncomplete,
                          self.imports.union(imports))

def combine(template, cs1, cs2):
    return CodeString(template % (cs1, cs2),
        cs1.uncomplete or cs2.uncomplete,
        union(cs1.imports, cs2.imports))
