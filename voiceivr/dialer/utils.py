import logging
import logging.handlers
import ConfigParser
import time
import os
import sys
import uuid
import md5
import json 

from twisted.internet import defer
from twisted.web.client import getPage

RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[%dm"
BOLD_SEQ = "\033[1m"
BLACK = 0
RED = 1
GREEN = 2
BROWN = 3
BLUE = 4
MEGENTA = 5
CYAN = 6
GRAY = 7

COLORS = {
    'WARNING': GREEN,
    'INFO': BROWN,
    'DEBUG': BLUE,
    'CRITICAL': GREEN,
    'ERROR': RED
}


class ColoredFormatter(logging.Formatter):
    def __init__(self, msg, use_color=True):
        logging.Formatter.__init__(self, msg)
        self.use_color = use_color

    def format(self, record):
        levelname = record.levelname
        prefix = ''
        suffix = ''
        if self.use_color and levelname in COLORS:
            prefix = COLOR_SEQ % (30+COLORS[levelname])
            suffix = RESET_SEQ
        msg = logging.Formatter.format(self, record)
        msg = prefix + msg + suffix
        return msg


def set_log_level(log):
    """
    log - target logger object on which log level needs to be set
    """
    config = get_config()
    # log_level should be any one of the following - DEBUG , INFO, ERROR, CRITICAL , FATAL
    log_level = config.get("general", "loglevel")
    log.setLevel(getattr(logging, log_level))


def get_logger(name):
    """
    Creates and sets log level on a python logger object 
    Returns the created logger object
    
    name - name of the logger to be created
    """
    log = logging.getLogger(name)
    set_log_level(log)
    return log


def get_post_vars(req):
    vars = {}
    for k, v in req.args.items():
        vars[k] = v[0]
    return vars


_config = None


def get_config():
    # Configure the global
    global _config
    if _config is None:
        filepath = "etc/dialer.conf"
        _config = Config(filepath)
        config_log()
    return _config


def getUUID():
    """
    Don't use uuid1 here. uuid1 return same uuid if there is no difference in time.
    This happens mostly when called in a loop
    """
    uid = uuid.uuid4()
    return str(uid)


def getUTC():
    """Return UTC in seconds"""
    return time.mktime(time.gmtime())


def calculateDigestResponse(username, realm, password, nonce, method, uri,
                            qop=None, cnonce=None, nc=None):
    """As of now FreeSWITCH and Asterisk seems to use qop=auth only no auth-int , so implementing 
    response calculation for qop=auth only."""
    md5new = md5.new  # to speed up things set a local reference
    ha1 = md5new("%s:%s:%s" % (username, realm, password))
    ha1 = ha1.hexdigest()
    ha2 = md5new("%s:%s" % (method, uri))
    ha2 = ha2.hexdigest()
    if qop == 'auth':
        response = md5new(
            "%s:%s:%s:%s:%s:%s" % (ha1, nonce, nc, cnonce, qop, ha2))
    else:
        response = md5new("%s:%s:%s" % (ha1, nonce, ha2))
    return response.hexdigest()


def config_log():
    """
    Configure logger
    """
    logpath = _config.get("general", "logpath")
    logfile = _config.get("general", "logfile")
    rootlogger = logging.getLogger('')
    fmt = logging.Formatter('%(asctime)s-%(name)s-%(levelname)s : %(message)s')
    cfmt = ColoredFormatter('(PID,%(process)d)-%(asctime)s-%(name)s-%(levelname)s : %(message)s')
    sh = logging.StreamHandler()
    sh.setFormatter(cfmt)
    rootlogger.addHandler(sh)
    logsize = _config.getint("general", "logsize")
    logbackupcount = _config.getint("general", "logbackupcount")
    rfh = logging.handlers.RotatingFileHandler(logpath+"/"+logfile, maxBytes=logsize, backupCount=logbackupcount)
    rfh.setFormatter(fmt)
    rootlogger.addHandler(rfh)


class Config(ConfigParser.ConfigParser):
    def __init__(self, filename):
        self.filename = filename
        ConfigParser.ConfigParser.__init__(self)
        self.load()

    def load(self):
        f = open(self.filename)
        self.readfp(f)
        f.close()


class InSequence(object):
    """Single-shot item creating a set of actions to run in sequence"""

    def __init__(self):
        self.actions = []
        self.results = []
        self.finalDF = None

    def append(self, function, *args, **named):
        """Append an action to the set of actions to process"""
        self.actions.append((function, args, named))

    def __call__(self):
        """Return deferred that fires when we are finished processing all items"""
        return self._doSequence()

    def _doSequence(self):
        """Return a deferred that does each action in sequence"""
        finalDF = defer.Deferred()
        self.onActionSuccess(None, finalDF=finalDF)
        return finalDF

    def recordResult(self, result):
        """Record the result for later"""
        self.results.append(result)
        return result

    def onActionSuccess(self, result, finalDF):
        """Handle individual-action success"""
        log.debug('onActionSuccess: %s', result)
        if self.actions:
            action = self.actions.pop(0)
            log.debug('action %s', action)
            df = defer.maybeDeferred(action[0], *action[1], **action[2])
            df.addCallback(self.recordResult)
            df.addCallback(self.onActionSuccess, finalDF=finalDF)
            df.addErrback(self.onActionFailure, finalDF=finalDF)
            return df
        else:
            finalDF.callback(self.results)

    def onActionFailure(self, reason, finalDF):
        """Handle individual-action failure"""
        log.debug('onActionFailure')
        reason.results = self.results
        finalDF.errback(reason)


class Signal():
    sighandlers = {}

    def __init__(self, signal):
        """

        @param signal: name of the signal
        """
        self.signal = signal

    def handler(self, func):
        """

        Register the signal handler
        """
        self.sighandlers.setdefault(self.signal, []).append(func)
        return func

    def send(self, sender=None, *args, **kwargs):
        """

        Send signal to all registered sighandlers
        """
        log.info("::::::   \tFiring SIGNAL SIGNAL SIGNAL %s\t  :::::::", self.signal)
        signal = self.signal
        try:
            sighandlers = self.sighandlers[signal]
        except KeyError as e:
            log.error("Signal not found with name %s", signal)
            return
        for i in sighandlers:
            log.debug("Calling signal: %s, args:%s kwargs:%s handler: %s",
                      signal, args, kwargs, i)
            i(sender, *args, **kwargs)

    registerHandler = handler


class HttpClient(object):

    def request(self, method, url, headers, post_data=None, final_df=None):
        log.debug("Sending Request %s: %s DATA: %s", method, url, post_data)
        method = method.upper()
        df = getPage(method=method,
                     url=url,
                     headers=headers,
                     postdata=post_data)
        df.addCallbacks(self.get_response, self.error_back)
        return df

    def get_response(self, response):
        log.debug("Raw Response In: %s\n %s", response, type(response))
        try:
            response = json.loads(response)
        except:
            log.error("Unable to parse response ")
        return response

    def error_back(self, error):
        log.exception("Error while sending request")
        return error.value.response, int(error.value.status)

http_client = HttpClient()


def sendRequest(method, url, headers, body=None):
    df = http_client.request(method, url, headers=headers, post_data=body)
    return df


config = get_config()
log = get_logger("utils")
