class OldStyle:
    def setx(self, x):
        self.x = x

class NewStyle(object):
    def __init__(self, x):
        self.x = x

    def incrx(self):
        self.x += 1

def main():
    o = OldStyle()
    o.setx(42)
    n = NewStyle(3)
    n.incrx()
