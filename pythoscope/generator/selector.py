from pythoscope.store import Call, Class, Definition, GeneratorObject, TestClass


def testable_objects(module):
    return [o for o in module.objects if is_testable_object(o)]

def is_testable_object(obj):
    if isinstance(obj, TestClass):
        return False
    elif isinstance(obj, Class):
        ignored_superclasses = ['Exception', 'unittest.TestCase']
        for klass in ignored_superclasses:
            if klass in obj.bases:
                return False
        return True
    elif isinstance(obj, Definition):
        return not obj.name.startswith('_')

def testable_calls(calls):
    return [c for c in calls if is_testable_call(c)]

def is_testable_call(call):
    if isinstance(call, GeneratorObject):
        return call.is_activated() and len(call.calls) > 0
    return True
