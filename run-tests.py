#!/usr/bin/python

import glob
import shutil
import sys

from os import system as run
from os import remove as rm

def cp(src, dst):
    shutil.copy(glob.glob(src)[0], dst)

def main():
    VERSIONS = [('2.3', ['tests', 'build']),
                ('2.4', ['tests', 'build']),
                ('2.5', ['tests'])]
    results = {}
 
    for ver, types in VERSIONS:
        if 'tests' in types:
            version = "%s-tests" % ver
            print "*** Running tests on Python %s without binary modules." % ver
            if run("nosetests-%s" % ver) == 0:
                results[version] = 'OK'
            else:
                results[version] = 'FAIL (tests)'

        if 'build' in types:
            version = "%s-build" % ver
            res1 = res2 = None
            print "*** Running tests on Python %s with binary modules." % ver
            res1 = run("python%s setup.py build -f" % ver)
            if res1 == 0:
                cp("build/lib.*-%s/pythoscope/_util.so" % ver, "pythoscope/")
                res2 = run("nosetests-%s" % ver)
                rm("pythoscope/_util.so")
            if res1 == 0 and res2 == 0:
                results[version] = 'OK'
            else:
                if res1 != 0:
                    results[version] = 'FAIL (compilation)'
                else:
                    results[version] = 'FAIL (tests)'

    print
    for ver, result in sorted(results.iteritems()):
        print "%s: %s" % (ver, result)

    if [v for v in results.values() if v != 'OK']:
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
