import logging
import time
import os
import sqlite3
import re
import socket
from pathlib import Path
from multiprocessing import Process, Event

import jinja2
import service
import openstack

from . import instances
from .constants import DATABASE_NAME
from .logger import initLogger


class Arboretum(service.Service):
    """
    A class used to represent the Arboretum daemon

    ...

    Methods
    -------
    run
        Main run loop of the daemon process used to setup processes
    getHealthString(process_health)
        Getter function that turns the processes' health into a String
    pruneLoop(exit_event)
        Exit Event checker & Wrapper function for pruneExpiredInstances
    updateLoop(exit_event)
        Exit Event checker & Wrapper function for updateBuildingInstances
    updateGroupsLoop(exit_event)
        Updates group database every hour checking for exit event during sleep phase
    pruneExpiredInstances
        Checks active instance's lifetime and destroys where appropriate


    """
    def __init__(self, working_dir, *args, **kwargs):
        """
        Parameters
        ----------
        working_dir : str
            z
        """
        super(Arboretum, self).__init__(*args, **kwargs)
]
        self.LOGGER_NAME = "daemon"
        self.logger = initLogger(self.LOGGER_NAME, "DAEMON")

        self.working_dir = working_dir
        self.db_path = Path(working_dir) / DATABASE_NAME

        if not self.db_path.exists():
            self.logger.error("ERROR! Database file {} not found!"
                .format(self.db_path))

        self.db_path = str(self.db_path)

    def run(self):
        """
        Main run loop of the daemon

        Sets up socket connection, establishes the processes and
        loops checking for a change of state

        Raises
        ------
        NameError
            If the socket or event doesn't exist
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                # creates IPv4 TCP socket for the daemon and CLI to talk over
                sock.bind(('127.0.0.1', 4510))
                sock.listen()
                sock.settimeout(1)

                exit_event = Event()
                self.logger.info("Starting daemon management processes.")

                process_map = {'prune_process': self.pruneLoop,
                    'instance_update_process': self.updateLoop,
                    'group_update_process': self.updateGroupsLoop}

                processes = {}
                for process_name in process_map.keys():
                    processes[process_name] = Process(
                        target=process_map[process_name],
                        args=(exit_event,), daemon=True)

                process_health = {}

                for process in processes.keys():
                    processes[process].start()
                    process_health[process] = "up"

                while not self.got_sigterm():
                    try:
                        # blocking socket with a second-long time out
                        conn, addr = sock.accept()
                        data = conn.recv(1024)
                        if data:
                            cmd = data.decode("UTF-8")
                            if cmd == "status":
                                response = self.getHealthString(process_health)
                                conn.sendall(response)
                        conn.close()
                    except socket.timeout:
                        pass

                    # Test for crashed processes, will crash silently otherwise
                    dead_procs = []
                    for process in processes.keys():
                        if not processes[process].is_alive():
                            self.logger.critical("CRITICAL: Process {}" \
                                "has died".format(process))
                            process_health[process] = "down"
                            dead_procs.append(process)

                    for process in dead_procs:
                        processes.pop(process)
                        # start a new process of the same type
                        replacement = Process(target=process_map[process],
                            args=(exit_event,), daemon=True)
                        replacement.start()
                        processes[process] = replacement
                        process_health[process] = "up"
                        self.logger.critical("Process {} has been revived."
                            .format(process))

                sock.close()

            self.logger.info("Terminating daemon management processes.")
            exit_event.set()

            for process in processes.values():
                process.join()
            self.logger.info("Exiting.")
        except Exception as e:
            try:
                sock.close()
            except NameError:
                pass

            try:
                exit_event.set()
                for process in processes.values():
                    process.join()
            except NameError:
                pass

            raise e

    def getHealthString(self, process_health):
        """
        Getter function that turns the processes' health into a String

        Parameters
        ----------
        process_health
            dictionary of processes and their status

        Returns
        -------
        string : str
            a string form of process_health
        """
        string = ""
        for process in process_health.keys():
            string += "{}={} ".format(process, process_health[process])
        string = string.strip().encode("UTF-8")
        return string

    def pruneLoop(self, exit_event):
        """
        Exit Event checker & Wrapper function for pruneExpiredInstances

        Parameters
        ----------
        exit_event
            Multiprocessing event that controls the running of the daemon's processes
        """
        while not exit_event.is_set():
            self.pruneExpiredInstances()
            time.sleep(2)

    def updateLoop(self, exit_event):
        """
        Exit Event checker & Wrapper function for updateBuildingInstances
        """
        while not exit_event.is_set():
            instances.updateBuildingInstances(self.db_path)
            time.sleep(5)

    def updateGroupsLoop(self, exit_event):
        """
        Updates group database every hour checking for exit event during sleep phase

        Parameters
        ----------
        exit_event
            Multiprocessing event that controls the running of the daemon's processes
        """
        while not exit_event.is_set():
            instances.generateGroupDatabase("daemon", db_name=self.db_path)
            # sleep for an hour, waking up every two seconds so that the exit
            # event can be checked
            count = 0
            while count < 3600:
                if exit_event.is_set():
                    break
                time.sleep(2)
                count += 2

    def pruneExpiredInstances(self):
        """
        Checks active instance's lifetime and destroys where appropriate
        """
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        cursor.execute('''SELECT instance_id, group_name, prune_time FROM
            branches WHERE prune_time <= datetime("now")''')

        for result in cursor:
            self.logger.info("{} instance has expired.\n\tPrune time: {}"
                .format(result[1], result[2]))

            instances.destroyInstance(result[1], "daemon", db_name=self.db_path)

        db.close()
