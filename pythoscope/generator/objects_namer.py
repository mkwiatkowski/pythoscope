from pythoscope.event import Event
from pythoscope.generator.dependencies import sorted_by_timestamp
from pythoscope.serializer import SerializedObject
from pythoscope.util import all_of_type, key_for_value, underscore


# :: SerializedObject -> str
def get_name_base_for_object(obj):
    common_names = {'list': 'alist',
                    'dict': 'adict',
                    'array.array': 'array',
                    'types.FunctionType': 'function',
                    'types.GeneratorType': 'generator'}
    return common_names.get(obj.type_name, underscore(obj.type_name))

# :: [str], str -> str
def get_next_name(names, base):
    """Figure out a new name starting with base that doesn't appear in given
    list of names.

    >>> get_next_name(["alist", "adict1", "adict2"], "adict")
    'adict3'
    """
    base_length = len(base)
    def has_right_base(name):
        return name.startswith(base)
    def get_index(name):
        return int(name[base_length:])
    return base + str(max(map(get_index, filter(has_right_base, names))) + 1)

# :: SerializedObject, {SerializedObject: str}, bool -> None
def assign_name_to_object(obj, assigned_names, rename=True):
    """Assign a right name for given object.

    May reassign an existing name for an object as a side effect, unless
    `rename` is False.
    """
    if assigned_names.has_key(obj):
        return
    base = get_name_base_for_object(obj)
    other_obj = key_for_value(assigned_names, base)

    if other_obj:
        # Avoid overlapping names by numbering objects with the same base.
        if rename:
            assigned_names[other_obj] = base+"1"
        assigned_names[obj] = base+"2"
    elif base+"1" in assigned_names.values():
        # We have some objects already numbered, insert a name with a new index.
        assigned_names[obj] = get_next_name(assigned_names.values(), base)
    else:
        # It's the first object with that base.
        assigned_names[obj] = base

# :: ([SerializedObject], {SerializedObject: str}), bool -> None
def assign_names_to_objects(objects, names, rename=True):
    """Modifies names dictionary as a side effect.
    """
    for obj in sorted_by_timestamp(objects):
        assign_name_to_object(obj, names, rename)

# :: [Event] -> [SerializedObject]
def objects_only(events):
    return all_of_type(events, SerializedObject)

class Assign(Event):
    def __init__(self, name, obj, timestamp):
        self.name = name
        self.obj = obj
        # We don't call Event.__init__ on purpose, we set our own timestamp.
        self.timestamp = timestamp

# :: [Event] -> [Event]
def name_objects_on_timeline(events):
    names = {}
    assign_names_to_objects(objects_only(events), names)
    def map_object_to_assign(event):
        if isinstance(event, SerializedObject):
            return Assign(names[event], event, event.timestamp)
        return event
    return map(map_object_to_assign, events)
