import logging
import time
import sys
import argparse
import sqlite3
import os
import sys
import subprocess
import re

import jinja2
import service
import openstack

import lib.db as db
from lib.arborist import Arboretum
from lib.logger import initLogger
from lib.constants import DATABASE_NAME

LOGGER_NAME = "cli"

parser = argparse.ArgumentParser(description="Arboretum - A system to start, monitor, and destroy OpenStack Branchserve instances.")

subparsers = parser.add_subparsers(dest='subparser')

parser_start = subparsers.add_parser('start',
    help="Start the Arboretum daemon")

parser_stop = subparsers.add_parser('stop',
    help="Stop the Arboretum demon")

parser_status = subparsers.add_parser('status',
    help="Print status of active instances to stdout.")
parser_status.add_argument('--tojson', dest='tojson', action='store_const',
    const=True, default=False, help="Format output as JSON.")
parser_status.add_argument('--totsv', dest='totsv', action='store_const',
    const=True, default=False, help="Format output as TSV.")

parser_instantiate = subparsers.add_parser('create',
    help="Create a new Branchserve instance on OpenStack")
parser_instantiate.add_argument('group', nargs=1,
    help="Unix group name to make an instance for")
parser_instantiate.add_argument('--lifetime', nargs='+',
    default=['8', 'hours'],
    help="How long Arboretum will wait before automatically destroying " \
        "the instance. Defaults to 8 hours.\nFormat: [xyz] minutes/hours/" \
        "days OR forever\nNote: [xyz] should be three digits maximum.")

parser_destroy = subparsers.add_parser('destroy',
    help="Destroy an existing Branchserve instance on Openstack")
parser_destroy.add_argument('group', nargs=1,
    help="Name of the Unix group whose instance will be destroyed")


def verifyLifetime(lifetime):
    """Syntax checker for the 'lifetime' argument."""
    if re.search("(^\d{1,3} (minutes?|hours?|days?)$)|(^forever$)", lifetime) is None:
        print("--lifetime argument {} isn't valid.\nFormat: [xyz] minutes/" \
            "hours/days OR forever\nNote: [xyz] should be three digits " \
            "maximum.".format(lifetime))

        sys.exit(1)
    else:
        return lifetime

if __name__ == '__main__':
    initLogger(LOGGER_NAME, "CLI")
    args = parser.parse_args()

    # daemon's working directory is root, so it needs the current working dir
    service = Arboretum(os.path.abspath(''), 'arboretum', pid_dir='/tmp')

    if args.subparser == "start":
        if service.is_running():
            print("Error: Arboretum daemon is already running at PID " \
                "{}.".format(service.get_pid()))
            exit(1)
        else:
            db.checkDB(DATABASE_NAME)
            db.initialiseDB()
            service.start()
            print("Daemon started successfully.")

    elif args.subparser == "stop":
        if not service.is_running():
            print("Error: Arboretum daemon is not running.")
            exit(1)
        else:
            service.stop()
            print("Daemon stopped successfully.")

    elif args.subparser == "create":
        go = True
        if not service.is_running():
            print("Warning: Arboretum daemon is not running, instances with " \
                "a set lifetime will not be automatically destroyed. Run " \
                "'arboretum start' to start the daemon.\nDo you want to " \
                "proceed anyway?\n\ny/N")
            choice = input("> ").lower()

            go = True if choice == "y" else False

        if go:
            lifetime = verifyLifetime(" ".join(args.lifetime))
            db.startInstance(args.group[0], lifetime)
        else:
            print("Exiting.")

    elif args.subparser == "destroy":
        service.destroyInstance(args.group[0], "cli")
