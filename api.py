import logging

import hug

import lib.db as db
from lib.logger import initLogger

LOGGER_NAME = "api"

initLogger(LOGGER_NAME, "API")

@hug.get('/groups')
def getGroups():
    return db.getGroups(True)

@hug.get('/create')
def createInstance(group):
    db.startInstance(group, "8 hours", "api")

@hug.get('/destroy')
def destroyInstance(group):
    db.destroyInstance(group, "api")

@hug.get('/lastmodified')
def getLastModifiedTime():
    return db.getLastModifiedTime()
