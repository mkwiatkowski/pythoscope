#!/usr/bin/env python
#
# Copyright 2009 Chad Daelhousen.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
#

import pythoscope
pythoscope.start()

import freshwall.core as core
from optparse import OptionValueError
import os.path
import sys


def parse_args (argv, parser=None):
    if parser is None:
        parser = core.get_parser(program=argv[0])

    # Prefs which change the overall operating mode
    parser.add_option("-d", "--daemon", action="store_true",
                      dest="daemon", default=False,
                      help="run in daemon mode")
    parser.add_option("-p", "--preferences", action="store_true",
                      dest="prefs", default=False,
                      help="open preferences window")
    parser.add_option("-x", "--exit-daemon", action="store_true",
                      dest="exit_daemon", default=False,
                      help="signal the daemon to shut down")

    # Daemon mode options
    parser.add_option("-D", "--no-detach", action="store_false",
                      dest="detach", default=True,
                      help="do not detach when running as a daemon")
    parser.add_option("-s", "--spread",
                      dest="spread", default="0", metavar="PERCENT",
                      help="amount of randomness of the period (0-100)")
    parser.add_option("-T", "--period",
                      dest="period", default="", metavar="TIME[d|h|m|s]",
                      help="average time between wallpaper changes")

    return parser.parse_args(argv[1:])


def run_prefs_gui (prefs):
    from freshwall import gui
    return gui.run_prefs_dialog(prefs)

def run_daemon (prefs, period, spread, detach):
    from freshwall import daemon
    return daemon.run(prefs, period, spread, detach)

def exit_daemon ():
    from freshwall import daemon
    return daemon.exit()


def main (argv=None):
    rv = 0
    if argv is None:
        argv = ['???']

    prefs = core.load_prefs()
    options, args = parse_args(argv)

    if options.prefs:
        rv = run_prefs_gui(prefs)
    elif options.exit_daemon:
        rv = exit_daemon()
    elif options.daemon:
        rv = run_daemon(prefs, options.period, options.spread, options.detach)
    else:
        core.change_wallpaper(prefs)

    # clean up
    prefs.nuke()
    pythoscope.stop()
    return rv


if __name__ == '__main__':
    sys.exit(main(sys.argv[:]))

