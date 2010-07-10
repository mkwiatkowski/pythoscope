import os

from pythoscope.compat import set


def python_modules_below(path):
    VCS_PATHS = set([".bzr", "CVS", "_darcs", ".git", ".hg", ".svn"])
    def is_python_module(path):
        return path.endswith(".py")
    def not_vcs_file(path):
        return not set(path.split(os.path.sep)).intersection(VCS_PATHS)
    return filter(not_vcs_file, filter(is_python_module, rlistdir(path)))

def rlistdir(path):
    """Resursive directory listing. Yield all files below given path,
    ignoring those which names begin with a dot.
    """
    if os.path.basename(path).startswith('.'):
        return

    if os.path.isdir(path):
        for entry in os.listdir(path):
            for subpath in rlistdir(os.path.join(path, entry)):
                yield subpath
    else:
        yield path
