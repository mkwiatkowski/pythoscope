import unittest

#for $object in $module.objects
class Test${camelize(object.name)}(unittest.TestCase):
#end for

if __name__ == '__main__':
    unittest.main()
