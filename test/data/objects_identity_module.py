class Facade(object):
    def __init__(self, system):
        self.system = system

    def just_do_it(self):
        self.system.do_this()
        self.system.do_that()

class System(object):
    def __init__(self, composite):
        self.composite = composite

    def do_this(self):
        self.composite.this()

    def do_that(self):
        self.composite.that()

class Composite(object):
    def __init__(self, objects):
        self.objects = objects

    def this(self):
        for obj in self.objects:
            obj.this()

    def that(self):
        for obj in self.objects:
            obj.that()

class Object(object):
    def __init__(self, x):
        self.x = x

    def this(self):
        pass

    def that(self):
        pass

def do_something_simple_with_system(system):
    facade = Facade(system)
    facade.just_do_it()

def main():
    objects = []
    for key in ["one", "two", "three"]:
        objects.append(Object(key))

    composite = Composite(objects)
    system = System(composite)

    do_something_simple_with_system(system)

if __name__ == '__main__':
    main()
