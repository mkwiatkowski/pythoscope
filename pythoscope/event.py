class Event(object):
    _last_timestamp = 0

    def __init__(self):
        self.timestamp = Event.next_timestamp()

    def next_timestamp(cls):
        cls._last_timestamp += 1
        return cls._last_timestamp
    next_timestamp = classmethod(next_timestamp)
