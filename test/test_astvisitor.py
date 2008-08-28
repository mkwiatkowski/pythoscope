from nose.tools import assert_equal

from pythoscope.astvisitor import parse, regenerate, ASTVisitor



class TestParser:
    def test_handles_inputs_without_newline(self):
        tree = parse("42 # answer")
        assert_equal("42 # answer", regenerate(tree))

class TestASTVisitor:
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

    def _test_import(self, code, method):
        class TestVisitor(ASTVisitor):
            def visit_import(self, names, import_from):
                method(names, import_from)
        TestVisitor().visit(parse(code))
