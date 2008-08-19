import unittest

#for $object in $module.objects
class Test${camelize(object.name)}(unittest.TestCase):
    #for $method in $object.test_methods
    def test_${method}(self):
        assert False # TODO: implement your test here

    #end for
#end for

if __name__ == '__main__':
    unittest.main()
