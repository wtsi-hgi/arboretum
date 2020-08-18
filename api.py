import logging

import hug

import lib.instances as instances
from lib.logger import initLogger

LOGGER_NAME = "api"

initLogger(LOGGER_NAME, "API")

@hug.get('/groups')
def getGroups():
    """
    Getter function for groups

    Returns
    -------
    instances.getGroups(True)
        List of groups
    """
    return instances.getGroups(True)

@hug.get('/activegroups')
def getActiveGroups():
    """
    Getter function for active groups

    Returns
    -------
    instances.getGroups(True, active_only=True)
        List of active groups
    """
    return instances.getGroups(True, active_only=True)

@hug.get('/create')
def createInstance(group):
    """
    Creates an instance of a given group with lifespan 8 hours

    Parameters
    ----------
    group
        Name of the Unix group to start an instance for
    """
    instances.startInstance(group, "8 hours", "api")

@hug.get('/destroy')
def destroyInstance(group):
    """
    Destroys an instance of a given group with lifespan 8 hours

    Parameters
    ----------
    group
        Name of the Unix group to start an instance for
    """
    instances.destroyInstance(group, "api")

@hug.get('/lastmodified')
def getStamp():
    """
    Returns integer stamp that changes after every database change

    Returns
    -------
    instances.getStamp()
        The value of the stamp
    """
    return instances.getStamp()
