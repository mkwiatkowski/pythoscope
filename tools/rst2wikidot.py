import re

from docutils.core import publish_cmdline, default_description
from docutils.nodes import NodeVisitor
from docutils.writers import Writer


class WikidotTranslator(NodeVisitor):
    """Write output in Wikidot format.

    Based on http://www.wikidot.com/doc:wiki-syntax
    """
    def __init__(self, document):
        NodeVisitor.__init__(self, document)

        self.section_level = 1
        self.first_paragraph = True
        self.inside_literal_block = False
        self.lists = []
        self.block_input = False
        self._content = []

    def get_text(self):
        return ''.join(self._content)

    def _add(self, string):
        if not self.block_input:
            self._content.append(string)

    def _nop(self, node):
        pass

    def _newline_if_not_first(self):
        if not self.first_paragraph:
            self._add("\n")

    visit_document = _nop
    depart_document = _nop

    def visit_section(self, node):
        self.section_level += 1
    def depart_section(self, node):
        self.section_level -= 1

    def visit_title(self, node):
        self._newline_if_not_first()
        self._add("+" * self.section_level + " ")
    def depart_title(self, node):
        self._add("\n")
        self.first_paragraph = False

    def visit_Text(self, node):
        string = node.astext()
        if not self.inside_literal_block:
            string = string.replace('\n', ' ')
        self._add(string)
    depart_Text = _nop

    def visit_paragraph(self, node):
        self._newline_if_not_first()
    def depart_paragraph(self, node):
        self._add("\n")
        self.first_paragraph = False

    def visit_strong(self, node):
        self._add("**")
    depart_strong = visit_strong

    def visit_reference(self, node):
        if node.has_key('name'):
            self._add("[%s " % node['refuri'])
    def depart_reference(self, node):
        if node.has_key('name'):
            self._add("]")

    visit_target = _nop
    depart_target = _nop

    def visit_literal_block(self, node):
        if re.search(r'(class )|(def )|(import )', node.astext()):
            self._add("\n[[code type=\"Python\"]]\n")
        else:
            self._add("\n[[code]]\n")
        self.inside_literal_block = True
    def depart_literal_block(self, node):
        self._add("\n[[/code]]\n")
        self.inside_literal_block = False

    def visit_topic(self, node):
        if 'contents' in node['classes']:
            self._add("[[toc]]\n")
        self.block_input = True
    def depart_topic(self, node):
        self.block_input = False

    def visit_bullet_list(self, node):
        self.lists.append('bullet')
    def depart_bullet_list(self, node):
        self.lists.pop()

    def visit_enumerated_list(self, node):
        self.lists.append('enumerated')
    def depart_enumerated_list(self, node):
        self.lists.pop()

    def visit_list_item(self, node):
        self._add(" " * (len(self.lists) - 1) * 2)
        if self.lists[-1] is 'enumerated':
            self._add("# ")
        else:
            self._add("* ")
        self.first_paragraph = True
    depart_list_item = _nop

class WikidotWriter(Writer):
    def translate(self):
        visitor = WikidotTranslator(self.document)
        self.document.walkabout(visitor)
        self.output = visitor.get_text()


if __name__ == '__main__':
    description = ('Generates documents in Wikidot format from standalone '
                   'reStructuredText sources. ' + default_description)
    publish_cmdline(writer=WikidotWriter(), description=description)

