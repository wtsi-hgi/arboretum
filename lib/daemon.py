import logging
import time
import os
import sqlite3
import re
from pathlib import Path
from multiprocessing import Process, Event

import jinja2
import service
import openstack

from . import instances
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
        exit_event = Event()
        self.logger.info("Starting daemon management processes.")
        prune_process = Process(target=self.pruneLoop, args=(exit_event,))
        update_process = Process(target=self.updateLoop, args=(exit_event,))
        group_loop = Process(target=self.updateGroupsLoop, args=(exit_event,))

        prune_process.start()
        update_process.start()
        group_loop.start()

        while not self.got_sigterm():
            time.sleep(1)

        self.logger.info("Terminating daemon management processes.")
        exit_event.set()
        prune_process.join()
        update_process.join()
        group_loop.join()
        self.logger.info("Exiting.")

    def pruneLoop(self, exit_event):
        while not exit_event.is_set():
            self.pruneExpiredInstances()
            time.sleep(2)

    def updateLoop(self, exit_event):
        while not exit_event.is_set():
            instances.updateBuildingInstances(self.db_path)
            time.sleep(5)

    def updateGroupsLoop(self, exit_event):
        while not exit_event.is_set():
            instances.generateGroupDatabase("daemon")
            # sleep for an hour, waking up every two seconds so that the daemon
            # takes less than an hour to terminate in the worst case
            time = 0
            while time < 3600:
                time.sleep(2)
                time += 2

    def pruneExpiredInstances(self):
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        cursor.execute('''SELECT instance_id, group_name, prune_time FROM
            branches WHERE prune_time <= datetime("now")''')

        for result in cursor:
            self.logger.info("{} instance has expired.\n\tPrune time: {}"
                .format(result[1], result[2]))

            instances.destroyInstance(result[1], "daemon", db_name=self.db_path)

        db.close()
