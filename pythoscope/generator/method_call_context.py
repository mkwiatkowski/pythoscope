class MethodCallContext(object):
    def __init__(self, call, user_object):
        self.call = call
        self.user_object = user_object

    def __getattr__(self, name):
        if name in ['input', 'definition', 'calls', 'args', 'output', 'timestamp']:
            return getattr(self.call, name)

    def __repr__(self):
        return "MethodCallContext(obj=%r, call=%r)" % (self.user_object, self.call)
