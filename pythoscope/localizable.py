import os
import time

from pythoscope.util import ensure_directory, get_last_modification_time, \
    module_path_to_name, write_content_to_file


class Localizable(object):
    """An object which has a corresponding file belonging to some Project.

    Each Localizable has a 'path' attribute and an information when it was
    created, to be in sync with its file system counterpart. Path is always
    relative to the project this localizable belongs to.
    """
    def __init__(self, project, subpath, created=None):
        self.project = project
        self.subpath = subpath
        if created is None:
            created = time.time()
        self.created = created

    def _get_locator(self):
        return module_path_to_name(self.subpath, newsep=".")
    locator = property(_get_locator)

    def is_out_of_sync(self):
        """Is the object out of sync with its file.
        """
        return get_last_modification_time(self.get_path()) > self.created

    def is_up_to_date(self):
        return not self.is_out_of_sync()

    def get_path(self):
        """Return the full path to the file.
        """
        return os.path.join(self.project.path, self.subpath)

    def write(self, new_content):
        """Overwrite the file with new contents and update its created time.

        Creates the containing directories if needed.
        """
        ensure_directory(os.path.dirname(self.get_path()))
        write_content_to_file(new_content, self.get_path())
        self.created = time.time()

    def exists(self):
        return os.path.isfile(self.get_path())
