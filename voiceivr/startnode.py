#!/usr/bin/python

import sys
import os
from twisted.application import service, internet
from twisted.python.log import PythonLoggingObserver
from twisted.cred import portal, checkers
from twisted.conch import manhole, manhole_ssh
from dialer import utils
from dialer.call import dialer
from dialer import xmlcurl
# from dialer import apiserver
# from dialer import outbound_socket
from dialer import incoming_call_outbound_socket
from dialer import inbound_socket
from twisted.scripts import twistd
# from dialer import  web_hooks   # Configure signal handlers
# from dialer import handlers
from dialer import json_server_spawn
from pyswitch import fsprotocol
import logging

sys.path.insert(0, os.getcwd())
fsprotocol.log.setLevel(logging.INFO)

config = utils.get_config()


def getManholeFactory(namespace, **passwords):
    realm = manhole_ssh.TerminalRealm()

    def getMahole(arg):
        return manhole.ColoredManhole(namespace)

    realm.chainedProtocolFactory.protocolFactory = getMahole
    p = portal.Portal(realm)
    p.registerChecker(
        checkers.InMemoryUsernamePasswordDatabaseDontUse(**passwords))
    f = manhole_ssh.ConchFactory(p)
    return f


log = utils.get_logger("Dialer")
observer = PythonLoggingObserver("Dialer")
observer.start()

manhole_service = internet.TCPServer(2024,
                                     getManholeFactory(globals(), admin='a&b'))
mainService = service.MultiService()
mainService.setName("Dialer")
mainService.addService(xmlcurl.getService(dialer))
mainService.addService(incoming_call_outbound_socket.getService(dialer))
mainService.addService(json_server_spawn.main(dialer))
mainService.addService(inbound_socket.getService(dialer))
mainService.addService(manhole_service)

application = service.Application("dialer")
mainService.setServiceParent(application)
sys.argv.append("-y dummy")

if os.name == 'posix':
    sys.argv.append("--logfile=/dev/null")
    sys.argv.append("--pidfile=run/dialer.pid")


class ApplicationRunner(twistd._SomeApplicationRunner):
    def createOrGetApplication(self):
        return application

    def run(self):
        self.preApplication()
        self.application = self.createOrGetApplication()
        self.postApplication()


twistd._SomeApplicationRunner = ApplicationRunner
# import profile
# profile.run(twistd.run())
twistd.run()
