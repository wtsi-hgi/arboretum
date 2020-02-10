import logging

import hug

import lib.db as db
from lib.logger import initLogger

LOGGER_NAME = "api"

initLogger(LOGGER_NAME, "API")

@hug.get('/groups')
def getGroups():
    return db.getGroups(True)
