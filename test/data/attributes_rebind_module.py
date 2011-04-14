class OldStyle:
    def setx(self, x):
        self.x = x

class NewStyle(object):
    def __init__(self, x):
        self.x = x
    def incrx(self):
        self.x += 1

class UsingOther(object):
    def create(self):
        other = NewStyle(13)
        other.incrx()
        return other
    def process(self, ns):
        ns.incrx()

class UsingOtherInternally(object):
    def __init__(self):
        self.internal = NewStyle(100)
    def use(self):
        self.internal.x += 111
        self.internal._y = 'private'

def main():
    o = OldStyle()
    o.setx(42)

    n = NewStyle(3)
    n.incrx()

    uo = UsingOther()
    uo.process(uo.create())

    uoi = UsingOtherInternally()
    uoi.use()

