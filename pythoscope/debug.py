from util import class_of


def print_assigned_names(assigned_names):
    print "ASSIGNED NAMES:"
    for obj, name in assigned_names.iteritems():
        print "    %s: %s(id=%s)" % (name, class_of(obj).__name__, id(obj))

def print_timeline(timeline):
    print "TIMELINE:"
    for event in timeline:
        print "    %5.2f: %r" % (event.timestamp, event)

