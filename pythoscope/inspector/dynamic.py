import sys

from pythoscope.tracer import ICallback, Tracer


class CallStack(object):
    def __init__(self):
        self.last_traceback = None
        self.stack = []
        self.top_level_calls = []

    def called(self, call):
        if self.stack:
            self.stack[-1].add_subcall(call)
        else:
            self.top_level_calls.append(call)
        self.stack.append(call)

    def returned(self, output):
        if self.stack:
            caller = self.stack.pop()
            caller.set_output(output)

            # If the last exception is reported by sys.exc_info() it means
            # it was handled inside the returning call.
            handled_traceback = sys.exc_info()[2]
            if handled_traceback is self.last_traceback:
                caller.clear_exception()

    def raised(self, exception, traceback):
        if self.stack:
            caller = self.stack[-1]
            caller.set_exception(exception)
            self.last_traceback = traceback

class Inspector(ICallback):
    """Controller of the dynamic inspection process. It receives information
    from the tracer and propagates it to Execution and CallStack objects.
    """
    def __init__(self, execution):
        self.execution = execution
        self.call_stack = CallStack()

    def finalize(self):
        # Copy the call graph structure to the Execution instance.
        self.execution.call_graph = self.call_stack.top_level_calls
        self.execution.finalize()

    def method_called(self, name, obj, args, code, frame):
        call = self.execution.create_method_call(name, obj, args, code, frame)
        return self.called(call)

    def function_called(self, name, args, code, frame):
        call = self.execution.create_function_call(name, args, code, frame)
        return self.called(call)

    def returned(self, output):
        self.call_stack.returned(self.execution.serialize(output))

    def raised(self, exception, traceback):
        self.call_stack.raised(self.execution.serialize(exception), traceback)

    def called(self, call):
        if call:
            self.call_stack.called(call)
            return True

def inspect_point_of_entry(point_of_entry):
    point_of_entry.clear_previous_run()

    # Put project's path into PYTHONPATH, so point of entry's imports work.
    sys.path.insert(0, point_of_entry.project.path)

    try:
        inspect_code_in_context(point_of_entry.get_content(),
                                point_of_entry.execution)
    finally:
        sys.path.remove(point_of_entry.project.path)

# :: (str, Execution) -> None
def inspect_code_in_context(code, execution):
    """Inspect given piece of code in the context of given Execution instance.

    May raise exceptions.
    """
    inspector = Inspector(execution)
    tracer = Tracer(inspector)
    try:
        tracer.trace(code)
    finally:
        inspector.finalize()
