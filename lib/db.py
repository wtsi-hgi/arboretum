import logging
import sqlite3
import os
import json

import jinja2
import openstack

from .constants import DATABASE_NAME

LOGGER_NAME = "cli"

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

    db.commit()
    db.close()

    logger = logging.getLogger(LOGGER_NAME)
    logger.info("Using {} as SQLite database file.".format(DATABASE_NAME))

def getGroups(jsonify):
    """Returns list of groups saved in the database.

    @param jsonify If True, returns list object. If False, returns
        tab-separated table string."""

    db = sqlite3.connect(DATABASE_NAME)
    cursor = db.cursor()

    # TODO: decide where/when to query the instance for its IP
    cursor.execute('''SELECT groups.group_name, groups.ram, groups.time,
        branches.prune_time, branches.creation_time, branches.status
        FROM groups LEFT OUTER JOIN branches
        ON groups.group_name = branches.group_name
        ORDER BY groups.group_name''')

    groups = []

    for group in cursor:
        entry = {'group_name': group[0], 'ram': group[1],
            'build_time': group[2], 'prune_time': group[3],
            'creation_time': group[4], 'status': group[5]}
        if entry['status'] != 'up':
            entry['status'] = 'down'

        groups.append(entry)

    db.close()

    if jsonify:
        # Hug automatically converts this to JSON for warden
        return groups
    else:
        tsv = "Group\tRAM needed\tTime to build"
        for group in groups:
            tsv += "\n{}\t{}\t{}".format(
                group['group_name'], group['ram'], group['time'])
        return tsv

def startInstance(group, lifetime):
    db = sqlite3.connect(DATABASE_NAME)
    cursor = db.cursor()

    cursor.execute('''SELECT * FROM branches WHERE group_name = ?''', (group,))

    if len(cursor.fetchall()) > 0:
        print("Can't create {} instance, one already exists!".format(group))
        sys.exit(1)

    cursor.execute('''SELECT * FROM groups WHERE group_name = ?''', (group,))

    if len(cursor.fetchall()) == 0:
        print("Can't create {} instance, group not recognised!".format(group))
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
    if lifetime == "forever":
        cursor.execute('''INSERT INTO branches(group_name, instance_ip,
            prune_time, instance_id, creation_time, status)
            VALUES(?, ?, ?, ?, datetime("now"), ?)''',
            (group, info.private_v4, "never", info.id, "up"))
            # TODO: 'status' should go from 'building' to 'up'
    else:
        cursor.execute('''INSERT INTO branches(group_name, instance_ip,
            prune_time, instance_id, creation_time, status)
            VALUES(?, ?, datetime("now", ?), ?, datetime("now"), ?)''',
            (group, info.private_v4, lifetime, info.id, "up"))

    db.commit()
    db.close()

    logger = logging.getLogger(LOGGER_NAME)
    logger.info("Created new Treeserve instance:\n\tID: {}\n\t" \
        "Group: {}\n\tLifetime: {}".format(info.id, group, lifetime))

    print("Created new Treeserve instance:\nID: {}\nGroup: {}\n" \
        "Lifetime: {}".format(info.id, group, lifetime))

def destroyInstance(group, caller):
    """ Destroys the instance for 'group'. The value of 'caller' is used to
    decide how to log messages.

    @param group Name of a Humgen Unix group
    @param caller If 'cli', the program prints to stdout. If anything else,
        it's passed to logging.getLogger to fetch a logger object"""
    if caller != "cli":
        logger = logging.getLogger(caller)

    db = sqlite3.connect(DATABASE_NAME)
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
        sys.exit(1)

    result = cursor.fetchall()

    # if the DB is fresh, it will be empty
    if [] == result:
        return name
    # if the DB was only used by Arboretum, it will have a "branches" table
    # and nothing else
    elif [('branches',), ('groups',)] == result:
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
