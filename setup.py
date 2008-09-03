from setuptools import setup

setup(
    name='pythoscope',
    version="0.2.2",

    author = 'Michal Kwiatkowski',
    author_email = 'constant.beta@gmail.com',
    description = 'unit test generator for Python',
    long_description = open("README").read() + "\n" + open("Changelog").read(),
    license = 'MIT',
    url = 'http://pythoscope.org',

    packages = ['pythoscope', 'lib2to3', 'lib2to3.pgen2'],
    package_data = {'pythoscope': [],
                    'lib2to3': ['*.txt']},
    install_requires = [],

    entry_points = {        
        'console_scripts': ['pythoscope = pythoscope:main']
    },

    test_suite = 'nose.collector',
    tests_require = ['nose', 'fixture'],

    classifiers = [
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Topic :: Software Development :: Code Generators',
        'Topic :: Software Development :: Testing',
    ],
)
