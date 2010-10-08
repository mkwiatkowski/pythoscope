def put_on_timeline(*objects):
    timestamp = 1
    for obj in objects:
        obj.timestamp = timestamp
        timestamp += 1
