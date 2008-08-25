#for $object in $module.testable_objects
#if $object.testable_methods
class Test${camelize(object.name)}:
    #for $method in $object.testable_methods
    def test_${method}(self):
        raise SkipTest # TODO: implement your test here

    #end for
#end if
#end for
