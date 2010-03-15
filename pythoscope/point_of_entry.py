from pythoscope.execution import Execution
from pythoscope.store import Localizable
from pythoscope.util import read_file_contents


class PointOfEntry(Localizable):
    """Piece of code provided by the user that allows dynamic analysis.

    Each point of entry keeps a reference to its last run in the `execution`
    attribute.
    """
    def __init__(self, project, name):
        Localizable.__init__(self, project, project.subpath_for_point_of_entry(name))

        self.project = project
        self.name = name
        self.execution = Execution(project)

    def _get_created(self):
        "Points of entry are not up-to-date until they're run."
        return self.execution.ended or 0
    def _set_created(self, value):
        pass
    created = property(_get_created, _set_created)

    def get_path(self):
        return self.project.path_for_point_of_entry(self.name)

    def get_content(self):
        return read_file_contents(self.get_path())

    def clear_previous_run(self):
        self.execution.destroy()
        self.execution = Execution(self.project)
