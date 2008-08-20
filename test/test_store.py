import os
from fixture import TempIO
from nose.tools import assert_equal

from pythoscope.store import Project, Module, Class, Function

class TestStore:
    def test_can_be_saved_and_restored_from_file(self):
        modules = [Module([Class("AClass", ["amethod"]), Function("afunction")]),
                   Module(errors=["Syntax error"])]
        project = Project(modules)
        tmpdir = TempIO()
        filepath = os.path.join(tmpdir, "project.pickle")

        project.save_to_file(filepath)
        project = Project(filepath=filepath)

        assert_equal(2, len(project.modules))
        assert_equal(2, len(project.modules[0].objects))
        assert_equal("AClass", project.modules[0].classes[0].name)
        assert_equal(["amethod"], project.modules[0].classes[0].methods)
        assert_equal("afunction", project.modules[0].functions[0].name)
        assert_equal(["Syntax error"], project.modules[1].errors)
