from lib2to3 import pygram
from lib2to3 import pytree
from lib2to3.patcomp import compile_pattern
from lib2to3.pgen2 import driver
from lib2to3.pgen2 import token
from lib2to3.pgen2.parse import ParseError


def parse(code):
    drv = driver.Driver(pygram.python_grammar, pytree.convert)
    return drv.parse_string(code, True)


class ASTError(Exception):
    pass
        
def is_leaf_of_type(leaf, *types):
    return isinstance(leaf, pytree.Leaf) and leaf.type in types

def is_node_of_type(node, *types):
    return isinstance(node, pytree.Node) and pytree.type_repr(node.type) in types

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

def derive_arguments(node):
    if node == []:
        return []
    elif is_node_of_type(node, 'typedargslist'):
        return map(derive_argument,
                   remove_defaults(remove_commas(node.children)))
    else:
        return [derive_argument(node)]

class ASTVisitor(object):
    DEFAULT_PATTERNS = [
        ('_visit_all', "file_input< nodes=any* >"),
        ('_visit_all', "suite< nodes=any* >"),
        ('_visit_class', "classdef< 'class' name=NAME ['(' bases=any ')'] ':' children=any >"),
        ('_visit_function', "funcdef< 'def' name=NAME parameters< '(' [args=any] ')' > ':' children=any >"),
        ('_visit_lambda_assign', "expr_stmt< name=NAME '=' lambdef< 'lambda' any ':' any > >"),
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
        if isinstance(tree, pytree.Leaf):
            self.visit_leaf(tree)
        elif isinstance(tree, pytree.Node):
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

    def visit_class(self, name, bases, children):
        self.visit(children)

    def visit_function(self, name, args, children):
        self.visit(children)

    def visit_lambda_assign(self, name):
        pass

    def _visit_all(self, results):
        self.visit(results['nodes'])

    def _visit_class(self, results):
        self.visit_class(name=results['name'].value,
                         bases=derive_class_names(results.get('bases')),
                         children=results['children'])

    def _visit_function(self, results):
        self.visit_function(name=results['name'].value,
                            args=derive_arguments(results.get('args', [])),
                            children=results['children'])

    def _visit_lambda_assign(self, results):
        self.visit_lambda_assign(name=results['name'].value)
