class Assertion(object):
    KNOWN_TYPES = (
        'missing',
        'comment',
        'equal',
        'equal_stub',
        'raises',
        'raises_stub')

    def __init__(self, type, args=(), setup=None):
        if type not in Assertion.KNOWN_TYPES:
            raise ValueError("Tried to create an assertion of unknown type %r." % type)
        self.type = type
        self.args = args
        self.setup = setup

    def has_code(self):
        return self.type in ['equal', 'missing', 'raises']
