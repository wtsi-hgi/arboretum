import logging
import sqlite3
import os
import json
import urllib.request
import subprocess
import re
import random
import math
from pathlib import Path

import jinja2
import openstack

from .constants import DATABASE_NAME

LOGGER_NAME = "cli"
RANDOM_RANGE = {'a':0, 'b':999999999999}

def initialiseDB():
    db = sqlite3.connect(DATABASE_NAME)
    cursor = db.cursor()

    try:
        cursor.execute('''CREATE TABLE branches(group_name TEXT PRIMARY KEY,
            instance_ip TEXT,
            prune_time TEXT,
            instance_id TEXT,
            creation_time TEXT,
            status TEXT)
        ''')
    except sqlite3.OperationalError:
        # this triggers when table "branches" already exists in the DB
        pass

    try:
        cursor.execute('''CREATE TABLE groups(group_name TEXT PRIMARY KEY,
            ram TEXT,
            time TEXT)
        ''')
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute('''CREATE TABLE info(name TEXT PRIMARY KEY,
            value TEXT)''')
        cursor.execute('''INSERT OR REPLACE INTO info
            VALUES ("stamp", ?)''', (random.randint(**RANDOM_RANGE),))
    except sqlite3.OperationalError:
        pass

    db.commit()
    db.close()

    logger = logging.getLogger(LOGGER_NAME)
    logger.info("Using {} as SQLite database file.".format(DATABASE_NAME))

def getStamp():
    """Returns integer stamp that changes after every database change"""
    db = sqlite3.connect(DATABASE_NAME)
    cursor = db.cursor()

    cursor.execute('''SELECT value FROM info WHERE name = "stamp"''')
    result = cursor.fetchone()[0]

    db.close()

    return result

def modifyStamp(db):
    """Change stamp to a new random integer"""
    cursor = db.cursor()

    cursor.execute('''INSERT OR REPLACE INTO info
        VALUES ("stamp", ?)''', (random.randint(**RANDOM_RANGE),))

    db.commit()

def getGroups(jsonify, active_only=False):
    """Returns list of groups saved in the database.

    @param jsonify If True, returns list object. If False, returns
        tab-separated table string."""

    db = sqlite3.connect(DATABASE_NAME)
    cursor = db.cursor()

    # TODO: decide where/when to query the instance for its IP
    cursor.execute('''SELECT groups.group_name, groups.ram, groups.time,
        branches.prune_time, branches.creation_time, branches.status,
        branches.instance_ip
        FROM groups LEFT OUTER JOIN branches
        ON groups.group_name = branches.group_name
        ORDER BY groups.group_name''')

    groups = {}

    for group in cursor:
        entry = {'group_name': group[0], 'ram': group[1],
            'build_time': group[2], 'prune_time': group[3],
            'creation_time': group[4], 'status': group[5],
            'instance_ip': group[6]}
        if entry['status'] == None:
            entry['status'] = 'down'

        if active_only and entry['status'] != 'down':
            groups[group[0]] = entry
        else:
            groups[group[0]] = entry

    db.close()

    if jsonify:
        # Hug automatically converts this to JSON for the API
        return groups
    else:
        tsv = "Group\tRAM needed\tTime to build"
        for group in groups.values():
            tsv += "\n{}\t{}\t{}".format(
                group['group_name'], group['ram'], group['time'])
        return tsv

def startInstance(group, lifetime, caller):
    """Start a Treeserve instance.

    @param group Name of the Unix group to start an instance for
    @param lifetime String indicating how long the instance will stay up
        before being automatically destroyed. For example: '8 hours',
        '25 minutes', 'forever'
    @param caller Either 'cli' or the name of a logger object. If 'cli',
        output will be printed to stdout, if anything else caller will
        be used as an argument to 'logging.getLogger()'
    """
    # this whole 'if caller != "cli"' thing feels ugly and redundant, but I'm
    # not sure how else to do it
    if caller != "cli":
        logger = logging.getLogger(caller)

    db = sqlite3.connect(DATABASE_NAME)
    cursor = db.cursor()

    cursor.execute('''SELECT * FROM branches WHERE group_name = ?''', (group,))

    if len(cursor.fetchall()) > 0:
        if caller == "cli":
            print("Can't create {} instance, one already exists!"
                .format(group))
        else:
            logger.warning("Can't create {} instance, one already exists!"
                .format(group))
        exit(1)

    cursor.execute('''SELECT group_name, ram
        FROM groups WHERE group_name = ?''', (group,))

    result = cursor.fetchall()[0]

    if len(result) == 0:
        if caller == "cli":
            print("Can't create {} instance, group not recognised!"
                .format(group))
        else:
            logger.warning("Can't create {} instance, group not recognised!"
                .format(group))
        exit(1)


    conn = openstack.connect(cloud='openstack')

    name = 'arboretum-{}-branch'.format(group)

    gib = 1024**3
    mib = 1024**2

    # extra GiB is added on top as headroom for system processes
    ram = int(result[1]) + gib

    # Defaults to using m1.small for groups requiring less than 14GiB of RAM
    # that way every instance has at least two cores
    if ram < 14*gib:
        flavor = 'm1.small'
    else:
        ram_mb = ram / mib
        # include="m" stops high core count o2 flavours from being used
        try:
            flavor = conn.get_flavor_by_ram(ram_mb, include="m").name
        except openstack.exceptions.SDKException:
            # SDKException will be thrown when no matching flavour is found,
            # then we try to get an s2 flavour instead
            flavor = conn.get_flavor_by_ram(ram_mb, include="s2").name

    jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(''))
    template = jinja_env.get_template('user.sh')

    userdata = template.render(group_name = group)

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
    # saved in the database.
    if lifetime == "forever":
        cursor.execute('''INSERT INTO branches(group_name, instance_ip,
            prune_time, instance_id, creation_time, status)
            VALUES(?, ?, ?, ?, datetime("now"), ?)''',
            (group, info.private_v4, "never", info.id, "building"))
    else:
        cursor.execute('''INSERT INTO branches(group_name, instance_ip,
            prune_time, instance_id, creation_time, status)
            VALUES(?, ?, datetime("now", ?), ?, datetime("now"), ?)''',
            (group, info.private_v4, lifetime, info.id, "building"))

    modifyStamp(db)

    db.commit()
    db.close()

    if caller == "cli":
        print("Created new Treeserve instance:\nID: {}\nGroup: {}\n" \
            "Lifetime: {}".format(info.id, group, lifetime))
    else:
        logger.info("Created new Treeserve instance:\n\tID: {}\n\t" \
            "Group: {}\n\tLifetime: {}".format(info.id, group, lifetime))

def updateBuildingInstances(db_name=DATABASE_NAME):
    # will probably only ever be called by the daemon
    logger = logging.getLogger("daemon")
    db = sqlite3.connect(db_name)
    cursor = db.cursor()

    cursor.execute('''SELECT group_name, instance_ip FROM branches
        WHERE status = "building"''')

    conn = openstack.connect(cloud='openstack')

    for branch in cursor:
        # try to find IP address if not recorded already
        if branch[1] == "":
            logger.info("Try to find IP for {}...".format(branch[0]))
            info = conn.get_server("arboretum-{}-branch"
                .format(branch[0]))

            if info is None:
                logger.info("Instance not ready.")
                continue

            if info.private_v4 == "":
                logger.info("No IP assigned yet.")
                continue

            cursor.execute('''UPDATE branches
                SET instance_ip = ?
                WHERE group_name = ?''', (info.private_v4, branch[0]))
            db.commit()
            logger.info("IP found successfully.")

        # use IP address to ping instance and find whether Treeserve is done
        if branch[1] != "":
            logger.info("Checking if {} is ready...".format(branch[0]))
            try:
                urllib.request.urlopen(
                    "http://{}:8080/api/v2".format(branch[1]))

                # if there's no error, Treeserve is ready
                cursor.execute('''UPDATE branches
                    SET status = "up"
                    WHERE group_name = ?''', (branch[0],))

                modifyStamp(db)
                db.commit()
                logger.info("Ready.")

            except urllib.error.URLError as e:
                if str(e) == "<urlopen error [Errno 111] Connection refused>":
                    logger.info("Treeserve not finished.")
                else:
                    raise e

    conn.close()
    db.close()

def generateGroupDatabase(caller):
    """Fetches mpistat chunks from S3 and creates a catalogue of
    available groups and estimates for their RAM and time requirements.
    """
    if caller != "cli":
        logger = logging.getLogger(caller)
        logger.info("Updating group database...")
    else:
        print("Updating group database...")

    try:
        output = subprocess.run(['s3cmd', 'get', '-f',
            's3://branchserve/mpistat/index.txt', '.'],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as error:
        if caller != "cli":
            logger.critical("s3cmd call failed!\n{}: {}"
                .format(type(error), error))
        else:
            print("s3cmd call failed!")
            raise error
        return

    if caller != "cli":
        logger.info("Index fetch complete.")
        logger.debug("s3cmd get output: {}"
            .format(output.stdout.decode("UTF-8")))
    else:
        print("Index fetch complete.")

    db = sqlite3.connect(DATABASE_NAME)
    cursor = db.cursor()

    # existing groups aren't relevant, for simplicity's sake we can just
    # nuke the groups table and populate it from scratch
    cursor.execute('''DELETE FROM groups''')
    with open("index.txt", "rt") as index:
        # skip the header
        index.readline()
        for line in index:
            _name, _time, _ram = line.split()

            _time = math.ceil(float(_time)/60)
            if _time == 1:
                _human_time = "1 minute"
            else:
                _human_time = "{} minutes".format(_time)

            cursor.execute('''INSERT INTO groups(group_name, ram, time)
                VALUES(?,?,?)''', (_name, _ram, _human_time))

            db.commit()

    if caller != "cli":
        logger.info("Group database generated successfully.")
    else:
        print("Group database generated successfully.")

    db.close()

def destroyInstance(group, caller, db_name=DATABASE_NAME):
    """ Destroys the instance for 'group'. The value of 'caller' is used to
    decide how to log messages.

    @param group Name of a Humgen Unix group
    @param caller If 'cli', the program prints to stdout. If anything else,
        it's passed to logging.getLogger to fetch a logger object"""
    if caller != "cli":
        logger = logging.getLogger(caller)

    db = sqlite3.connect(db_name)
    cursor = db.cursor()

    cursor.execute('''SELECT group_name, instance_id FROM branches WHERE
        group_name = ?''', (group,))

    result = cursor.fetchall()

    if len(result) == 0:
        if caller == "cli":
            print("{} instance not found in the database. The instance " \
                "was either already destroyed or never created in the " \
                "first place.".format(group))
        else:
            logger.warning("{} instance not found in the database."
                .format(group))

        return False

    server_id = result[0][1]

    conn = openstack.connect(cloud='openstack')
    success = conn.delete_server(server_id)
    conn.close()

    if not success:
        if caller == "cli":
            print("Can't destroy {} instance, it doesn't exist."
                .format(group))
        else:
            logger.warning("Can't destroy {} instance, it doesn't exist."
                .format(group))
    else:
        if caller == "cli":
            print("{} instance destroyed.".format(group))
        else:
            logger.warning("{} instance destroyed successfully.".format(group))

    cursor.execute('''DELETE FROM branches WHERE group_name = ?''', (group,))
    modifyStamp(db)

    db.commit()
    db.close()

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
        exit(1)

    result = cursor.fetchall()

    # if the DB is fresh, it will be empty
    if [] == result:
        return name
    # if the DB was only used by Arboretum, it will have a "branches" table
    # and nothing else
    elif [('branches',), ('groups',), ('info',)] == result:
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
            exit()
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
            exit()
