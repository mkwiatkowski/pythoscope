from pythoscope.compat import any, set
from pythoscope.util import union


class CodeString(str):
    """A string that holds information on the piece of code (like a function
    or method call) it represents.

    `uncomplete` attribute denotes whether it is a complete, runnable code
    or just a template.

    `imports` is a set of imports that this piece of code requires.
    """
    def __new__(cls, string, uncomplete=False, imports=None):
        if imports is None:
            imports = set()
        code_string = str.__new__(cls, string)
        code_string.uncomplete = uncomplete
        code_string.imports = imports
        return code_string

def combine_two_code_strings(template, cs1, cs2):
    return CodeString(template % (cs1, cs2),
        cs1.uncomplete or cs2.uncomplete,
        union(cs1.imports, cs2.imports))

def combine_string_and_code_string(template, s, cs):
    return CodeString(template % (s, cs), cs.uncomplete, cs.imports)

def combine(cs1, cs2, template="%s%s"):
    """Concatenate two CodeStrings, or a string and a CodeString, preserving
    information on `uncomplete` and `imports`.
    """
    if isinstance(cs1, CodeString) and isinstance(cs2, CodeString):
        return combine_two_code_strings(template, cs1, cs2)
    elif type(cs1) is str:
        return combine_string_and_code_string(template, cs1, cs2)

def join(char, code_strings):
    return CodeString(char.join(code_strings),
        any([cs.uncomplete for cs in code_strings]),
        union(*[cs.imports for cs in code_strings]))

def putinto(cs, template, imports):
    """Put the CodeString into a template, adding additional imports.
    """
    return CodeString(template % cs, cs.uncomplete, union(cs.imports, imports))
