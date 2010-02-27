from pythoscope.store import Call, Callable, Class, GeneratorObject, TestClass


def testable_objects(module):
    return [o for o in module.objects if is_testable(o)]

def is_testable(obj):
    if isinstance(obj, TestClass):
        return False
    elif isinstance(obj, Class):
        ignored_superclasses = ['Exception', 'unittest.TestCase']
        for klass in ignored_superclasses:
            if klass in obj.bases:
                return False
        return True
    elif isinstance(obj, Callable):
        return not obj.name.startswith('_')
    elif isinstance(obj, GeneratorObject):
        return obj.raised_exception() or obj.output
    elif isinstance(obj, Call):
        return True

def testable_calls(calls):
    return [c for c in calls if is_testable(c)]
