import logging
import time
import sys
import argparse
import sqlite3
import os
import sys
import subprocess
import re
import socket

import jinja2
import openstack

import lib.instances as instances
from lib.daemon import Arboretum
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
    help="Print daemon status to stdout.")

parser_active = subparsers.add_parser('active',
    help="Print status of active instances to stdout.")

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

parser_update = subparsers.add_parser('update',
    help="Update catalogue of S3 mpistat chunks.")

parser_groups = subparsers.add_parser('groups',
    help="Print a list of available groups and their requirements.")

def verifyLifetime(lifetime):
    """Syntax checker for the 'lifetime' argument."""
    if re.search("(^\d{1,3} (minutes?|hours?|days?)$)|(^forever$)", lifetime) is None:
        print("--lifetime argument {} isn't valid.\nFormat: [xyz] minutes/" \
            "hours/days OR forever\nNote: [xyz] should be three digits " \
            "maximum.".format(lifetime))

        exit(1)
    else:
        return lifetime

def getDaemonStatus():
    service = Arboretum(os.path.abspath(''), 'arboretum', pid_dir='/tmp',
        signals=[10])

    if service.is_running():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect(('127.0.0.1', 4510))
            sock.send(b'status')
            data = sock.recv(1024)
        return data.decode("UTF-8")
    else:
        return "down"

if __name__ == '__main__':
    initLogger(LOGGER_NAME, "CLI")
    args = parser.parse_args()

    # daemon's working directory is root, so it needs the current working dir
    # signal 10 (SIGUSR1) is used for user-defined signals
    service = Arboretum(os.path.abspath(''), 'arboretum', pid_dir='/tmp',
        signals=[10])

    if args.subparser == "start":
        if service.is_running():
            print("Error: Arboretum daemon is already running at PID " \
                "{}.".format(service.get_pid()))
            exit(1)
        else:
            instances.checkDB(DATABASE_NAME)
            instances.initialiseDB()
            service.start()

            time.sleep(1)
            if service.is_running():
                print("Daemon started successfully.")
            else:
                print("Daemon failed to start or crashed soon after launch! " \
                    "See the 'arboretum.log' file for details.")

    elif args.subparser == "stop":
        if not service.is_running():
            print("Error: Arboretum daemon is not running. If you think it " \
                "should be, check the 'arboretum.log' file to see if/why " \
                "it crashed.")
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
            instances.startInstance(args.group[0], lifetime, "cli")
        else:
            print("Exiting.")

    elif args.subparser == "status":
        if service.is_running():
            print("Running. Status:")
            _status = getDaemonStatus()
            for line in _status.split():
                print("- {}".format(line))
        else:
            print("Inactive.")

    elif args.subparser == "destroy":
        instances.destroyInstance(args.group[0], "cli")

    elif args.subparser == "update":
        instances.generateGroupDatabase("cli")

    elif args.subparser == "groups":
        print(instances.getGroups(False))

    elif args.subparser == "active":
        print(instances.getGroups(False, active_only=True))
