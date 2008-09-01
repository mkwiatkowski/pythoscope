#if $object.get_testable_methods
class ${test_name}(unittest.TestCase):
    #for $method in $object.get_testable_methods
    def test_${method}(self):
        assert False # TODO: implement your test here

    #end for
#end if
