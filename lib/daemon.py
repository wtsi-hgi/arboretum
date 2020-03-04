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
        processes = {}
        processes['prune_process'] = Process(
            target=self.pruneLoop, args=(exit_event,), daemon=True)
        processes['update_process'] = Process(
            target=self.updateLoop, args=(exit_event,), daemon=True)
        processes['group_loop'] = Process(
            target=self.updateGroupsLoop, args=(exit_event,), daemon=True)

        for process in processes.values():
            process.start()

        while not self.got_sigterm():
            time.sleep(1)
            # Test for crashed processes, will crash silently otherwise
            dead_procs = []
            for process in processes.keys():
                if not processes[process].is_alive():
                    self.logger.critical("Process {} has died!"
                        .format(process))
                    dead_procs.append(process)

            for process in dead_procs:
                processes.pop(process)

        self.logger.info("Terminating daemon management processes.")
        exit_event.set()

        for process in processes.values():
            process.join()
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
            instances.generateGroupDatabase("daemon", db_name=self.db_path)
            # sleep for an hour, waking up every two seconds so that the daemon
            # takes less than an hour to terminate in the worst case
            count = 0
            while count < 3600:
                if exit_event.is_set():
                    break
                time.sleep(2)
                count += 2

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
