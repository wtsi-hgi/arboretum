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
    const=True, default=False, help="Format output as JSON.")
parser_status.add_argument('--totsv', dest='totsv', action='store_const',
    const=True, default=False, help="Format output as TSV.")

parser_instantiate = subparsers.add_parser('create',
    help="Create a new Branchserve instance on OpenStack")
parser_instantiate.add_argument('group', nargs=1,
    help="Unix group name to make an instance for")
parser_instantiate.add_argument('--lifetime', nargs='+', default='8 hours',
    help="How long Arboretum will wait before automatically destroying " \
        "the instance. Defaults to 8 hours.\nFormat: [xyz] minutes/hours/" \
        "days OR forever\nNote: [xyz] should be three digits maximum.")

parser_destroy = subparsers.add_parser('destroy',
    help="Destroy an existing Branchserve instance on Openstack")
parser_destroy.add_argument('group', nargs=1,
    help="Name of the Unix group whose instance will be destroyed")


class Arboretum(service.Service):
    def __init__(self, db_name, *args, **kwargs):
        super(Arboretum, self).__init__(*args, **kwargs)

        log_handler = logging.FileHandler(filename='arboretum.log')
        log_formatter = logging.Formatter(fmt="DAEMON: %(message)s")

        log_handler.setFormatter(log_formatter)
        self.logger.addHandler(log_handler)

        self.logger.setLevel(logging.INFO)

        self.db_name = db_name

    def run(self):
        while not self.got_sigterm():
            time.sleep(2)
            self.destroyExpiredInstances()

    def destroyExpiredInstances(self):
        db = sqlite3.connect(self.db_name)
        cursor = db.cursor()

        cursor.execute('''SELECT instance_id, group_name, prune_time FROM
            branches WHERE prune_time <= datetime("now")''')

        for result in cursor:
            self.logger.info("{} instance has expired.\n\tPrune time: {}\n\t" \
                "Current time: {}".format(
                    result[1], result[2],
                    time.strftime("%H:%M:%S", time.gmtime()) ))

            self.destroyInstance(result[1], "daemon")

        db.close()

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

    def destroyInstance(self, group, caller):
        # This function is part of the daemon class because it's usable
        # directly from the cli or as part of the daemon's loop. It doesn't
        # have to be here, but I thought it would be more convenient
        db = sqlite3.connect(DATABASE_NAME if caller == "cli" else self.db_name)
        cursor = db.cursor()

        cursor.execute(''' SELECT group_name, instance_id FROM branches WHERE
            group_name = ?''', (group,))

        result = cursor.fetchall()

        if len(result) == 0:
            if caller == "daemon":
                self.logger.warning("{} instance not found in the " \
                    "database.".format(group))
            elif caller == "cli":
                print("{} instance not found in the database. The instance " \
                    "was either already destroyed or never created in the" \
                    "first place.".format(group))

            return False

        # result is a tuple in a list
        server_id = result[0][1]

        conn = openstack.connect(cloud='openstack')
        success = conn.delete_server(server_id)
        conn.close()

        if not success:
            if caller == "daemon":
                self.logger.warning("Can't destroy {} instance, it doesn't " \
                    "exist.".format(group))
            elif caller == "cli":
                print("Can't destroy {} instance, it doesn't exist.".format(
                    group))
        else:
            if caller == "daemon":
                self.logger.info("{} instance destroyed.".format(group))
            elif caller == "cli":
                print("{} instance destroyed successfully.".format(group))

        cursor.execute('DELETE FROM branches WHERE group_name = ?', (group,))

        db.commit()
        db.close()

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

def startInstance(group, lifetime):
    db = sqlite3.connect(DATABASE_NAME)
    cursor = db.cursor()

    cursor.execute('''SELECT * FROM branches WHERE group_name = ?''', (group,))

    if len(cursor.fetchall()) > 0:
        print("Can't create {} instance, one already exists!".format(group))
        sys.exit(1)

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
    conn.close()

    # OpenStack takes its time allocating the IP, so info.private_v4 will most
    # likely be None here. It will be looked up again when necessary and
    # cached in the database.
    cursor.execute('''INSERT INTO branches(group_name, instance_ip,
        prune_time, instance_id)
        VALUES(?, ?, datetime("now", ?), ?)''',
        (group, info.private_v4, lifetime, info.id))

    db.commit()
    db.close()

    logger = logging.getLogger(__name__)
    logger.info("Created new Treeserve instance:\n\tID: {}\n\t" \
        "Group: {}\n\tLifetime: {}".format(info.id, group, lifetime))

    print("Created new Treeserve instance:\nID: {}\nGroup: {}\n" \
        "Lifetime: {}".format(info.id, group, lifetime))

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

def verifyLifetime(lifetime):
    """Syntax checker for the 'lifetime' argument."""
    if re.search("(^\d{1,3} (minutes?|hours?|days?)$)|(^forever$)", lifetime) is None:
        print("--lifetime argument {} isn't valid.\nFormat: [xyz] minutes/" \
            "hours/days OR forever\nNote: [xyz] should be three digits " \
            "maximum.".format(lifetime))

        sys.exit(1)
    else:
        return lifetime

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

    # daemon's working directory is root, so it needs the DB's absolute path
    service = Arboretum(os.path.abspath(DATABASE_NAME), 'arboretum',
        pid_dir='/tmp')

    if args.subparser == "start":
        checkDB(DATABASE_NAME)
        initialiseDB()
        service.start()
        print("Daemon started successfully.")

    elif args.subparser == "stop":
        service.stop()
        print("Daemon stopped successfully.")

    elif args.subparser == "create":
        lifetime = verifyLifetime(" ".join(args.lifetime))
        startInstance(args.group[0], lifetime)

    elif args.subparser == "destroy":
        service.destroyInstance(args.group[0], "cli")
