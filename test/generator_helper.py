from pythoscope.store import FunctionCall

from factories import create


def put_on_timeline(*objects):
    timestamp = 1
    for obj in objects:
        obj.timestamp = timestamp
        timestamp += 1

def create_parent_call_with_side_effects(call, side_effects):
    parent_call = create(FunctionCall)
    parent_call.add_subcall(call)
    map(parent_call.add_side_effect, side_effects)
