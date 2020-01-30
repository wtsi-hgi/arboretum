import logging
import time
import sys
import argparse
import sqlite3
import os
import sys
import subprocess

import jinja2
import service
import openstack

DATABASE_NAME = "_arboretum_database.db"

parser = argparse.ArgumentParser(description="Arboretum - A system to start, monitor, and destroy OpenStack Branchserve instances.")

subparsers = parser.add_subparsers(dest='subparser')

parser_start = subparsers.add_parser('start',
    help="Start the Arboretum daemon")

parser_stop = subparsers.add_parser('stop',
    help="Stop the Arboretum demon")

parser_status = subparsers.add_parser('status',
    help="Print status of active instances to stdout.")
parser_status.add_argument('--tojson', dest='tojson', action='store_const',
    const=True, default=True, help="Format output to JSON.")

parser_instantiate = subparsers.add_parser('create',
    help="Create a new Branchserve instance on OpenStack")
parser_instantiate.add_argument('group', nargs=1,
    help="Unix group name to make an instance for")

parser_destroy = subparsers.add_parser('destroy',
    help="Destroy an existing Branchserve instance on Openstack")
parser_destroy.add_argument('group', nargs=1,
    help="Name of the Unix group whose instance will be destroyed")


class Arboretum(service.Service):
    def __init__(self, *args, **kwargs):
        super(Arboretum, self).__init__(*args, **kwargs)

        log_handler = logging.FileHandler(filename='arboretum.log')
        log_formatter = logging.Formatter(fmt="DAEMON: %(message)s")

        log_handler.setFormatter(log_formatter)
        self.logger.addHandler(log_handler)

        self.logger.setLevel(logging.INFO)

        self.db_name = DATABASE_NAME

    def run(self):
        while not self.got_sigterm():
            # Right now, the daemon doesn't actually do anything
            time.sleep(1)

    def estimateRequirements(self):
        """ Fetches all the mpistat chunks in S3 and uses them to create a
        catalogue of available groups and estimate the RAM and time needed
        to run Treeserve on them
        """
        self.logger.info("Running s3cmd sync...")

        output = subprocess.run(['s3cmd', 'sync', '--no-preserve',
            's3://branchserve/mpistat/', './mpistat/'], check=True,
            stdout=subprocess.PIPE)

        self.logger.info("s3cmd sync complete.")
        self.logger.debug("s3cmd sync output: {}".format(
            output.stdout.decode("UTF-8")))

def initialiseDB():
    db = sqlite3.connect(DATABASE_NAME)
    cursor = db.cursor()

    try:
        cursor.execute('''CREATE TABLE branches(group_name TEXT PRIMARY KEY,
            instance_ip TEXT,
            prune_time TEXT,
            instance_id TEXT)
        ''')
    except sqlite3.OperationalError:
        # this triggers when table "branches" already exists in the DB
        pass

    db.commit()
    db.close()

    logger = logging.getLogger(__name__)
    logger.info("Using {} as SQLite database file.".format(DATABASE_NAME))

def startInstance(group):
    name = 'arboretum-{}-branch'.format(group)
    # TODO: implement process to estimate requirements for each group
    flavor = 'm2.small'

    jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(''))
    template = jinja_env.get_template('user.sh')

    userdata = template.render(group_name = group)

    conn = openstack.connect(cloud='openstack')

    info = conn.create_server(name=name,
        image='hgi-branchserve-host',
        flavor=flavor,
        network='cloudforms_network',
        security_groups=['default', 'cloudforms_web_in',
            'cloudforms_ssh_in', 'cloudforms_local_in'],
        userdata=userdata)

    db = sqlite3.connect(DATABASE_NAME)
    cursor = db.cursor()

    # OpenStack takes its time allocating the IP, so info.private_v4 will most
    # likely be None here. It will be looked up again when necessary and
    # cached in the database.
    cursor.execute('''INSERT INTO branches(group_name, instance_ip,
        prune_time, instance_id)
        VALUES(?, ?, time("now", "+12 hours"), ?)''',
        (group, info.private_v4, info.id))

    db.commit()
    db.close()

    logger = logging.getLogger(__name__)
    logger.info("Created new Treeserve instance:\nID: {}\n" \
        "Group: {}".format(info.id, group))

    print("Created new Treeserve instance:\nID: {}\n" \
        "Group: {}".format(info.id, group))

def checkDB(name):
    """ Checks whether the DB file called 'name' already exists, and asks the
    user how to proceed if it does. Returns the name of a clean SQLite DB for
    the daemon to use.
    """

    db = sqlite3.connect(name)
    cursor = db.cursor()

    # check whether the file name points to an existing file
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    except sqlite3.DatabaseError:
        print("{} not recognised as a database file. Please delete or move " \
            "the file and try again.".format(name))
        sys.exit(1)

    result = cursor.fetchall()

    # if the DB is fresh, it will be empty
    if [] == result:
        return name
    # if the DB was only used by Arboretum, it will have a "branches" table
    # and nothing else
    elif [('branches',)] == result:
        print("""
Database file {} already exists. What do you want to do?

(O) - Overwrite the file
(R) - Restore state from the file

(any other input) - Cancel
        """.format(name))

        choice = input("> ").lower()

        if choice == "o":
            db.close()
            os.remove(name)

            return name
        elif choice == "r":
            # the daemon handles restoring state
            return name
        else:
            print("Exiting...")
            sys.exit()
    else:
        print("""
File {} already exists and appears to be an unrecognised SQLite
database. Do you want to overwrite the file?

(yes) - Yes
(any other input) - No
        """.format(name))

        choice = input("> ").lower()

        if choice == "yes":
            db.close()
            os.remove(name)

            return name
        else:
            print("Please move or rename the file and start Arboretum again.")
            sys.exit()

def initLogger():
    _log_handler = logging.FileHandler(filename='arboretum.log')
    _log_formatter = logging.Formatter(fmt="CLI: %(message)s")

    _log_handler.setFormatter(_log_formatter)
    LOGGER = logging.getLogger(__name__)
    LOGGER.addHandler(_log_handler)
    LOGGER.setLevel(logging.INFO)

if __name__ == '__main__':
    initLogger()
    args = parser.parse_args()

    service = Arboretum('arboretum', pid_dir='/tmp')

    if args.subparser == "start":
        checkDB(DATABASE_NAME)
        initialiseDB()
        service.start()
        print("Daemon started successfully.")

    elif args.subparser == "stop":
        service.stop()
        print("Daemon stopped successfully.")

    elif args.subparser == "create":
        startInstance(args.group[0])

    elif args.subparser == "destroy":
        pass
