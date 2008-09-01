import os
import re

# Portability code.
try:
    set = set
except NameError:
    from sets import Set as set


def camelize(name):
    """Covert name into CamelCase.

    >>> camelize('underscore_name')
    'UnderscoreName'
    >>> camelize('AlreadyCamelCase')
    'AlreadyCamelCase'
    >>> camelize('')
    ''
    """
    def upcase(match):
        return match.group(1).upper()
    return re.sub(r'(?:^|_)(.)', upcase, name)


def underscore(name):
    """Convert name into underscore_name.

    >>> underscore('CamelCase')
    'camel_case'
    >>> underscore('already_underscore_name')
    'already_underscore_name'
    >>> underscore('BigHTMLClass')
    'big_html_class'
    >>> underscore('')
    ''
    """
    if name and name[0].isupper():
        name = name[0].lower() + name[1:]

    def capitalize(match):
        string = match.group(1).capitalize()
        return string[:-1] + string[-1].upper()

    def underscore(match):
        return '_' + match.group(1).lower()

    name = re.sub(r'([A-Z]+)', capitalize, name)
    return re.sub(r'([A-Z])', underscore, name)

def read_file_contents(filename):
    fd = file(filename)
    contents = fd.read()
    fd.close()
    return contents

def write_string_to_file(string, filename):
    fd = file(filename, 'w')
    fd.write(string)
    fd.close()

def python_sources_below(path):
    return [os.path.join(path, entry) for entry in os.listdir(path) if entry.endswith(".py")]

def max_by_not_zero(func, collection):
    """Return the element of a collection for which func returns the highest
    value, greater than 0.

    Return None if there is no such value.

    >>> max_by_not_zero(len, ["abc", "d", "ef"])
    'abc'
    >>> max_by_not_zero(lambda x: x, [0, 0, 0, 0]) is None
    True
    >>> max_by_not_zero(None, []) is None
    True
    """
    if not collection:
        return None

    def annotate(element):
        return (func(element), element)

    highest = max(map(annotate, collection))
    if highest and highest[0] > 0:
        return highest[1]
    else:
        return None
