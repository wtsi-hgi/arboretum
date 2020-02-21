import logging

import hug

import lib.instances as instances
from lib.logger import initLogger

LOGGER_NAME = "api"

initLogger(LOGGER_NAME, "API")

@hug.get('/groups')
def getGroups():
    return instances.getGroups(True)

@hug.get('/activegroups')
def getActiveGroups():
    return instances.getGroups(True, active_only=True)

@hug.get('/create')
def createInstance(group):
    instances.startInstance(group, "8 hours", "api")

@hug.get('/destroy')
def destroyInstance(group):
    instances.destroyInstance(group, "api")

@hug.get('/lastmodified')
def getLastModifiedTime():
    return instances.getLastModifiedTime()
