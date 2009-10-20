from pythoscope.astvisitor import ASTVisitor
from pythoscope.astbuilder import parse, regenerate

from assertions import *


class TestASTVisitorImports:
    def test_handles_simple_imports(self):
        code = "import unittest"
        def assertions(names, import_from):
            assert_equal(["unittest"], names)
            assert_equal(None, import_from)

        self._test_import(code, assertions)

    def test_handles_multiple_imports(self):
        code = "import unittest, nose"
        def assertions(names, import_from):
            assert_equal(["unittest", "nose"], names)
            assert_equal(None, import_from)

        self._test_import(code, assertions)

    def test_handles_deep_imports(self):
        code = "import abc.xyz.FBR"
        def assertions(names, import_from):
            assert_equal(["abc.xyz.FBR"], names)
            assert_equal(None, import_from)

        self._test_import(code, assertions)

    def test_handles_multiple_deep_imports(self):
        code = "import abc.xyz, abc.zyx"
        def assertions(names, import_from):
            assert_equal(["abc.xyz", "abc.zyx"], names)
            assert_equal(None, import_from)

        self._test_import(code, assertions)

    def test_handles_from_imports(self):
        code = "from nose import SkipTest"
        def assertions(names, import_from):
            assert_equal(["SkipTest"], names)
            assert_equal("nose", import_from)

        self._test_import(code, assertions)

    def test_handles_multiple_from_imports(self):
        code = "from nose import SkipTest, DeprecatedTest"
        def assertions(names, import_from):
            assert_equal(["SkipTest", "DeprecatedTest"], names)
            assert_equal("nose", import_from)

        self._test_import(code, assertions)

    def test_handles_deep_from_imports(self):
        code = "from nose.tools import assert_equal"
        def assertions(names, import_from):
            assert_equal(["assert_equal"], names)
            assert_equal("nose.tools", import_from)

        self._test_import(code, assertions)

    def test_handles_imports_with_as(self):
        code = "import unittest as test"
        def assertions(names, import_from):
            assert_equal([("unittest", "test")], names)
            assert_equal(None, import_from)

        self._test_import(code, assertions)

    def test_handles_multiple_imports_with_as(self):
        code = "import X as Y, A as B"
        def assertions(names, import_from):
            assert_equal([("X", "Y"), ("A", "B")], names)
            assert_equal(None, import_from)

        self._test_import(code, assertions)

    def _test_import(self, code, method):
        method_called = [False]
        class TestVisitor(ASTVisitor):
            def visit_import(self, names, import_from, body):
                method(names, import_from)
                method_called[0] = True

        TestVisitor().visit(parse(code))
        assert method_called[0], "visit_import wasn't called at all"

class TestASTVisitorMainSnippet:
    def test_detects_the_main_snippet(self):
        code = "import unittest\n\nif __name__ == '__main__':\n    unittest.main()\n"
        def assertions(body):
            assert_equal("\nif __name__ == '__main__':\n    unittest.main()\n", body)

        self._test_main_snippet(code, assertions)

    def test_detects_main_snippet_with_different_quotes(self):
        code = 'import unittest\n\nif __name__ == "__main__":\n    unittest.main()\n'
        def assertions(body):
            assert_equal('\nif __name__ == "__main__":\n    unittest.main()\n', body)

        self._test_main_snippet(code, assertions)

    def _test_main_snippet(self, code, method):
        method_called = [False]
        class TestVisitor(ASTVisitor):
            def visit_main_snippet(self, body):
                method(regenerate(body))
                method_called[0] = True

        TestVisitor().visit(parse(code))
        assert method_called[0], "visit_main_snippet wasn't called at all"
