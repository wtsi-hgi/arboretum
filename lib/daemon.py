import logging
import time
import subprocess
import os
import sqlite3
import re
from pathlib import Path

import jinja2
import service
import openstack

from . import db
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
            if self.got_signal(10):
                self.clear_signal(10)
                self.generateGroupDatabase()
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

            db.destroyInstance(result[1], "daemon")

        db.close()

    def generateGroupDatabase(self):
        """Fetches mpistat chunks from S3 and creates a catalogue of
        available groups and estimates for their RAM and time requirements.
        """
        self.logger.info("Running s3cmd sync.")

        try:
            # FIXME: this seems to randomly fail whenever trying to sync new
            # files to a directory which has already been synced before.
            # Seems to work if it's re-run a few times though
            output = subprocess.run(['s3cmd', 'sync', '--no-preserve',
                '--no-check-md5', 's3://branchserve/mpistat/', './mpistat/'],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=self.working_dir)
        except subprocess.CalledProcessError as error:
            self.logger.critical("s3cmd call failed!\n{}: {}"
                .format(type(error), error))
            return

        self.logger.info("s3cmd sync complete.")
        self.logger.debug("s3cmd sync output: {}"
            .format(output.stdout.decode("UTF-8")))

        group_files = os.listdir(Path(self.working_dir) / "mpistat")

        extension = re.compile('\.dat\.gz$')

        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        # existing groups aren't relevant, for simplicity's sake we can just
        # nuke the groups table and populate it from scratch
        cursor.execute('''DELETE FROM groups''')
        # removes file extensions to get list of available groups
        for file in group_files:
            if extension.search(file):
                _name = extension.sub("", file)
                cursor.execute('''INSERT INTO groups(group_name, ram, time)
                    VALUES(?,?,?)''', (_name, "0GB", "0 minutes"))

                db.commit()
            else:
                self.logger.warning("File {} found in mpistat chunk " \
                    "directory, doesn't have '.dat.gz' extension!"
                    .format(file))

        self.logger.info("Group database generated successfully.")
        db.close()
        # TODO: properly estimate requirements, schedule it based on new data
        # going into S3
