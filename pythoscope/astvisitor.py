from pythoscope.logger import log
from pythoscope.util import quoted_block

from lib2to3 import pygram
from lib2to3 import pytree
from lib2to3.patcomp import compile_pattern
from lib2to3.pgen2 import driver
from lib2to3.pgen2 import token
from lib2to3.pgen2.parse import ParseError
from lib2to3.pygram import python_symbols as syms
from lib2to3.pytree import Node, Leaf


__all__ = ["EmptyCode", "Newline", "clone", "create_import", "parse",
           "regenerate", "ASTError", "ASTVisitor"]

EmptyCode = lambda: Node(syms.file_input, [])
Newline = lambda: Leaf(token.NEWLINE, "\n")

def clone(tree):
    """Clone the tree, preserving its add_newline attribute.
    """
    if tree is None:
        return None

    new_tree = tree.clone()
    if hasattr(tree, 'added_newline') and tree.added_newline:
        new_tree.added_newline = True
    return new_tree

def create_import(import_desc):
    """Create an AST representing import statement from given description.

    >>> regenerate(create_import("unittest"))
    'import unittest\\n'
    >>> regenerate(create_import(("nose", "SkipTest")))
    'from nose import SkipTest\\n'
    """
    if isinstance(import_desc, tuple):
        package, name = import_desc
        return Node(syms.import_from,
                    [Leaf(token.NAME, 'from'),
                     Leaf(token.NAME, package, prefix=" "),
                     Leaf(token.NAME, 'import', prefix=" "),
                     Leaf(token.NAME, name, prefix=" "),
                     Newline()])
    else:
        return Node(syms.import_name,
                    [Leaf(token.NAME, 'import'),
                     Leaf(token.NAME, import_desc, prefix=" "),
                     Newline()])

def descend(tree, visitor_type):
    """Walk over the AST using a visitor of a given type and return the visitor
    object once done.
    """
    visitor = visitor_type()
    visitor.visit(tree)
    return visitor

def find_last_leaf(node):
    if isinstance(node, Leaf):
        return node
    else:
        return find_last_leaf(node.children[-1])

def get_starting_whitespace(code):
    whitespace = ""
    for child in code.children:
        if is_leaf_of_type(child, token.NEWLINE, token.INDENT):
            whitespace += child.value
        else:
            break
    return whitespace

def remove_trailing_whitespace(code):
    leaf = find_last_leaf(code)
    leaf.prefix = leaf.prefix.replace(' ', '').replace('\t', '')

def parse(code):
    """String -> AST

    Parse the string and return its AST representation. May raise
    a ParseError exception.
    """
    added_newline = False
    if not code.endswith("\n"):
        code += "\n"
        added_newline = True

    try:
        drv = driver.Driver(pygram.python_grammar, pytree.convert)
        result = drv.parse_string(code, True)
    except ParseError:
        log.debug("Had problems parsing:\n%s\n" % quoted_block(code))
        raise

    # Always return a Node, not a Leaf.
    if isinstance(result, Leaf):
        result = Node(syms.file_input, [result])

    result.added_newline = added_newline

    return result

def parse_fragment(code):
    """Works like parse() but returns an object stripped of the file_input
    wrapper. This eases merging this piece of code into other ones.
    """
    parsed_code = parse(code)

    if is_node_of_type(parsed_code, 'file_input') and \
           len(parsed_code.children) == 2 and \
           is_leaf_of_type(parsed_code.children[-1], token.ENDMARKER):
        return parsed_code.children[0]
    return parsed_code

def regenerate(tree):
    """AST -> String

    Regenerate the source code from the AST tree.
    """
    if hasattr(tree, 'added_newline') and tree.added_newline:
        return str(tree)[:-1]
    else:
        return str(tree)

class ASTError(Exception):
    pass

def is_leaf_of_type(leaf, *types):
    return isinstance(leaf, Leaf) and leaf.type in types

def is_node_of_type(node, *types):
    return isinstance(node, Node) and pytree.type_repr(node.type) in types

def leaf_value(leaf):
    return leaf.value

def remove_commas(nodes):
    def isnt_comma(node):
        return not is_leaf_of_type(node, token.COMMA)
    return filter(isnt_comma, nodes)

def remove_defaults(nodes):
    ignore_next = False
    for node in nodes:
        if ignore_next is True:
            ignore_next = False
            continue
        if is_leaf_of_type(node, token.EQUAL):
            ignore_next = True
            continue
        yield node

def derive_class_name(node):
    if is_leaf_of_type(node, token.NAME, token.DOT):
        return node.value
    elif is_node_of_type(node, 'power', 'trailer'):
        return "".join(map(derive_class_name, node.children))
    else:
        raise ASTError("Unknown node type: %r." % node)

def derive_class_names(node):
    if node is None:
        return []
    elif is_node_of_type(node, 'arglist'):
        return map(derive_class_name, remove_commas(node.children))
    else:
        return [derive_class_name(node)]

def derive_argument(node):
    if is_leaf_of_type(node, token.NAME):
        return node.value
    elif is_node_of_type(node, 'tfpdef'):
        return tuple(map(derive_argument,
                         remove_commas(node.children[1].children)))

def derive_arguments_from_typedargslist(typedargslist):
    prefix = ''
    for node in remove_defaults(remove_commas(typedargslist.children)):
        if is_leaf_of_type(node, token.STAR):
            prefix = '*'
        elif is_leaf_of_type(node, token.DOUBLESTAR):
            prefix = '**'
        elif prefix:
            yield prefix + derive_argument(node)
            prefix = ''
        else:
            yield derive_argument(node)

def derive_arguments(node):
    if node == []:
        return []
    elif is_node_of_type(node, 'typedargslist'):
        return list(derive_arguments_from_typedargslist(node))
    else:
        return [derive_argument(node)]

def derive_import_name(node):
    if is_leaf_of_type(node, token.NAME):
        return node.value
    elif is_node_of_type(node, 'dotted_as_name'):
        return (derive_import_name(node.children[0]),
                derive_import_name(node.children[2]))
    elif is_node_of_type(node, 'dotted_name'):
        return "".join(map(leaf_value, node.children))

def derive_import_names(node):
    if node is None:
        return None
    elif is_node_of_type(node, 'dotted_as_names', 'import_as_names'):
        return map(derive_import_name,
                   remove_commas(node.children))
    else:
        return [derive_import_name(node)]


class ASTVisitor(object):
    DEFAULT_PATTERNS = [
        ('_visit_all', "file_input< nodes=any* >"),
        ('_visit_all', "suite< nodes=any* >"),
        ('_visit_class', "body=classdef< 'class' name=NAME ['(' bases=any ')'] ':' any >"),
        ('_visit_function', "body=funcdef< 'def' name=NAME parameters< '(' [args=any] ')' > ':' any >"),
        ('_visit_import', "import_name< 'import' names=any > | import_from< 'from' import_from=any 'import' names=any >"),
        ('_visit_lambda_assign', "expr_stmt< name=NAME '=' lambdef< 'lambda' [args=any] ':' any > >"),
        ('_visit_main_snippet', "body=if_stmt< 'if' comparison< '__name__' '==' (\"'__main__'\" | '\"__main__\"' ) > ':' any >"),
    ]

    def __init__(self):
        self.patterns = []
        for method, pattern in self.DEFAULT_PATTERNS:
            self.register_pattern(method, pattern)

    def register_pattern(self, method, pattern):
        """Register method to handle given pattern.
        """
        self.patterns.append((method, compile_pattern(pattern)))

    def visit(self, tree):
        """Main entry point of the ASTVisitor class.
        """
        if isinstance(tree, Leaf):
            self.visit_leaf(tree)
        elif isinstance(tree, Node):
            self.visit_node(tree)
        elif isinstance(tree, list):
            for subtree in tree:
                self.visit(subtree)
        else:
            raise ASTError("Unknown tree type: %r." % tree)

    def visit_leaf(self, leaf):
        pass

    def visit_node(self, node):
        for method, pattern in self.patterns:
            results = {}
            if pattern.match(node, results):
                getattr(self, method)(results)
                break
        else:
            # For unknown nodes simply descend to their list of children.
            self.visit(node.children)

    def visit_class(self, name, bases, body):
        self.visit(body.children)

    def visit_function(self, name, args, body):
        self.visit(body.children)

    def visit_import(self, names, import_from):
        pass

    def visit_lambda_assign(self, name, args):
        pass

    def visit_main_snippet(self, body):
        pass

    def _visit_all(self, results):
        self.visit(results['nodes'])

    def _visit_class(self, results):
        self.visit_class(name=results['name'].value,
                         bases=derive_class_names(results.get('bases')),
                         body=results['body'])

    def _visit_function(self, results):
        self.visit_function(name=results['name'].value,
                            args=derive_arguments(results.get('args', [])),
                            body=results['body'])

    def _visit_import(self, results):
        self.visit_import(names=derive_import_names(results['names']),
                          import_from=derive_import_name(results.get('import_from')))

    def _visit_lambda_assign(self, results):
        self.visit_lambda_assign(name=results['name'].value,
                                 args=derive_arguments(results.get('args', [])))

    def _visit_main_snippet(self, results):
        self.visit_main_snippet(body=results['body'])
