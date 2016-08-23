from module import Facade
import unittest
from module import Object
from module import Composite
from module import System
from module import do_something_simple_with_system
from module import main


class TestFacade(unittest.TestCase):
    def test_just_do_it_returns_None_after_creation_with_system_instance(self):
        alist = [Object('one'), Object('two'), Object('three')]
        composite = Composite(alist)
        system = System(composite)
        facade = Facade(system)
        self.assertEqual(None, facade.just_do_it())

class TestSystem(unittest.TestCase):
    def test_do_that_and_do_this_after_creation_with_composite_instance(self):
        alist = [Object('one'), Object('two'), Object('three')]
        composite = Composite(alist)
        system = System(composite)
        self.assertEqual(None, system.do_this())
        self.assertEqual(None, system.do_that())

class TestComposite(unittest.TestCase):
    def test_that_and_this_after_creation_with_list(self):
        alist = [Object('one'), Object('two'), Object('three')]
        composite = Composite(alist)
        self.assertEqual(None, composite.this())
        self.assertEqual(None, composite.that())

class TestObject(unittest.TestCase):
    def test_that_and_this_after_creation_with_one(self):
        object = Object('one')
        self.assertEqual(None, object.this())
        self.assertEqual(None, object.that())

    def test_that_and_this_after_creation_with_three(self):
        object = Object('three')
        self.assertEqual(None, object.this())
        self.assertEqual(None, object.that())

    def test_that_and_this_after_creation_with_two(self):
        object = Object('two')
        self.assertEqual(None, object.this())
        self.assertEqual(None, object.that())

class TestDoSomethingSimpleWithSystem(unittest.TestCase):
    def test_do_something_simple_with_system_returns_None_for_system_instance(self):
        alist = [Object('one'), Object('two'), Object('three')]
        composite = Composite(alist)
        self.assertEqual(None, do_something_simple_with_system(System(composite)))

class TestMain(unittest.TestCase):
    def test_main_returns_None(self):
        self.assertEqual(None, main())

if __name__ == '__main__':
    unittest.main()
