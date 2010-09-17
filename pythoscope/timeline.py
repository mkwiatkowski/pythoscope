class Timeline(object):
    def __init__(self):
        self._last_timestamp = 0

    def put(self, obj):
        obj.timestamp = self.next_timestamp()

    def next_timestamp(self):
        self._last_timestamp += 1
        return self._last_timestamp
