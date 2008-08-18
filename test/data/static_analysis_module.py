class SimpleClass(object):
    def simple_method(self):
        pass

    def method_with_one_arg(self, argument):
        pass

class ClassWithInit(object):
    def __init__(self):
        self.attr = 42

    def method(self, arg):
        self.attr += arg

class OldStyleClass:
    def m(self):
        pass

class EmptyClass(object):
    class_attr = 13

class SubclassOfEmpty(EmptyClass):
    def new_method(self):
        pass

def stand_alone_function(arg1, arg2):
    def inner_function(arg):
        pass
    class InnerClass(object):
        pass
    pass

class TopLevelClass(object):
    class AnotherInnerClass(object):
        pass
    def method(self):
        pass
