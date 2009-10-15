import os

from nose import SkipTest

from pythoscope.util import read_file_contents


def test_documentation_syntax():
    # May not be present in all distributions (added to stdlib in Python 2.5).
    try:
        import docutils.parsers.rst
        import docutils.utils
    except ImportError:
        raise SkipTest

    def test(doc):
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, doc))

        parser = docutils.parsers.rst.Parser()
        contents = read_file_contents(path)

        document = docutils.utils.new_document(path)
        document.settings.tab_width = 4
        document.settings.pep_references = 1
        document.settings.rfc_references = 1

        # Will raise exception on a mere warning from the parser.
        document.reporter.halt_level = 0

        parser.parse(contents, document)

    for doc in ["README", "Changelog", "doc/FAQ", "doc/basic-tutorial.txt"]:
        yield test, doc
