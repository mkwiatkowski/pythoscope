from nose import SkipTest

#for $object in $module.test_objects
#if $object.test_methods
class Test${camelize(object.name)}:
    #for $method in $object.test_methods
    def test_${method}(self):
        raise SkipTest # TODO: implement your test here

    #end for
#end if
#end for
