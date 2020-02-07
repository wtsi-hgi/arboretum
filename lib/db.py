import logging
import sqlite3
import os

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
            creation_time TEXT)
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
    if lifetime == "forever":
        cursor.execute('''INSERT INTO branches(group_name, instance_ip,
            instance_id, creation_time)
            VALUES(?, ?, ?, datetime("now"))''',
            (group, info.private_v4, info.id))
    else:
        cursor.execute('''INSERT INTO branches(group_name, instance_ip,
            prune_time, instance_id, creation_time)
            VALUES(?, ?, datetime("now", ?), ?, datetime("now"))''',
            (group, info.private_v4, lifetime, info.id))

    db.commit()
    db.close()

    logger = logging.getLogger(LOGGER_NAME)
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
