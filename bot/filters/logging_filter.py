"""
AUTHOR CODE - V1N3R
TG: @v1n3r
Site Company: buy-bot.ru
"""

import logging


class ApschedulerCleaner(logging.Filter):
    def filter(self, record):
        keywords = ['load_db_texts', 'Looking', 'Next wakeup is']
        write = True
        for elem in keywords:
            if elem in record.getMessage():
                write = False
                break
        return write


def set_logging_filter(logging_object):
    logging_object.getLogger('apscheduler.scheduler').addFilter(ApschedulerCleaner())
    logging_object.getLogger('apscheduler.executors.default').addFilter(ApschedulerCleaner())
