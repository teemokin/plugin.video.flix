import logging

import xbmc
import xbmcaddon
import xbmcgui

from lib.utils import PY3, str_to_unicode

ADDON = xbmcaddon.Addon()
ADDON_NAME = ADDON.getAddonInfo("name")
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_PATH = str_to_unicode(ADDON.getAddonInfo("path"))
ADDON_ICON = str_to_unicode(ADDON.getAddonInfo("icon"))
ADDON_DATA = str_to_unicode(xbmc.translatePath(ADDON.getAddonInfo("profile")))

set_setting = ADDON.setSetting
get_setting = ADDON.getSetting
open_settings = ADDON.openSettings

if PY3:
    translate = ADDON.getLocalizedString
else:
    def translate(*args, **kwargs):
        return ADDON.getLocalizedString(*args, **kwargs).encode("utf-8")


def notification(message, heading=ADDON_NAME, icon=ADDON_ICON, time=5000, sound=True):
    xbmcgui.Dialog().notification(heading, message, icon, time, sound)


def get_boolean_setting(setting):
    return get_setting(setting) == "true"


def get_int_setting(setting):
    return int(get_setting(setting))


def get_float_setting(setting):
    return float(get_setting(setting))


def set_boolean_setting(setting, value):
    set_setting(setting, "true" if value else "false")


class KodiLogHandler(logging.StreamHandler):
    levels = {
        logging.CRITICAL: xbmc.LOGFATAL,
        logging.ERROR: xbmc.LOGERROR,
        logging.WARNING: xbmc.LOGWARNING,
        logging.INFO: xbmc.LOGINFO,
        logging.DEBUG: xbmc.LOGDEBUG,
        logging.NOTSET: xbmc.LOGNONE,
    }

    def __init__(self):
        super(KodiLogHandler, self).__init__()
        self.setFormatter(logging.Formatter("[{}] %(message)s".format(ADDON_ID)))

    def emit(self, record):
        xbmc.log(self.format(record), self.levels[record.levelno])

    def flush(self):
        pass


def set_logger(name=None, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.addHandler(KodiLogHandler())
    logger.setLevel(level)