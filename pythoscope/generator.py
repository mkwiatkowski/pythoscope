import os

from Cheetah import Template

def template_path(name):
    "Return a path to the given template."
    return os.path.join(os.path.dirname(__file__), "templates/%s.tpl" % name)

def generate_test_module(module, template="unittest"):
    return str(Template.Template(file=template_path(template),
                                 searchList=[locals()]))
