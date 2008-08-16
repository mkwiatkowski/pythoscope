from setuptools import setup

setup(
    name='pythoscope',
    version="0.1",

    author = 'Michal Kwiatkowski',
    author_email = 'constant.beta@gmail.com',
    description = 'unit tests generator for Python',
    license = 'GPLv3',
    url = 'http://pythoscope.org',

    packages = ['pythoscope'],

    test_suite = 'nose.collector',
    tests_require = ['nose'],
)
