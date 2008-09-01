#if $object.get_testable_methods
class ${$test_name}:
    #for $method in $object.get_testable_methods
    def test_${method}(self):
        raise SkipTest # TODO: implement your test here

    #end for
#end if
