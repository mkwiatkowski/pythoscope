import unittest

#for $object in $module.testable_objects
#if $object.testable_methods
class Test${camelize(object.name)}(unittest.TestCase):
    #for $method in $object.testable_methods
    def test_${method}(self):
        assert False # TODO: implement your test here

    #end for
#end if
#end for
if __name__ == '__main__':
    unittest.main()
