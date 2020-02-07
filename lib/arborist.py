import logging
import time
import subprocess
import sqlite3
from pathlib import Path

import jinja2
import service
import openstack

from .constants import DATABASE_NAME
from .logger import initLogger


class Arboretum(service.Service):
    def __init__(self, working_dir, *args, **kwargs):
        super(Arboretum, self).__init__(*args, **kwargs)

        self.LOGGER_NAME = "daemon"
        self.logger = initLogger(self.LOGGER_NAME, "DAEMON")

        self.working_dir = working_dir
        self.db_path = Path(working_dir) / DATABASE_NAME

        if not self.db_path.exists():
            self.logger.error("ERROR! Database file {} not found!"
                .format(self.db_path))

        self.db_path = str(self.db_path)

    def run(self):
        while not self.got_sigterm():
            time.sleep(2)
            self.pruneExpiredInstances()

    def pruneExpiredInstances(self):
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        cursor.execute('''SELECT instance_id, group_name, prune_time FROM
            branches WHERE prune_time <= datetime("now")''')

        for result in cursor:
            self.logger.info("{} instance has expired.\n\tPrune time: {}"
                .format(result[1], result[2]))

            self.destroyInstance(result[1], "daemon")

        db.close()

    def generateGroupDatabase(self):
        """Fetches mpistat chunks from S3 and creates a catalogue of
        available groups and estimates for their RAM and time requirements.
        """
        self.logger.info("Running s3cmd sync.")

        output = subprocess.run(['s3cmd', 'sync', '--no-preserve',
            's3://branchserve/mpistat/', './mpistat/'], check=True,
            stdout=subprocess.PIPE, cwd=self.working_dir)

        self.logger.info("s3cmd sync complete.")
        self.logger.debug("s3cmd sync output: {}"
            .format(output.stdout.decode("UTF-8")))

        # TODO

    def destroyInstance(self, group, caller):
        # This function is part of the daemon class because it's usable
        # directly from the cli or as part of the daemon's loop. It doesn't
        # have to be here, but I thought it would be more convenient
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        cursor.execute('''SELECT group_name, instance_id FROM branches WHERE
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
