#!/usr/bin/python

import sys
import os
from twisted.application import service, internet
from twisted.python.log import PythonLoggingObserver
from twisted.cred import portal, checkers
from twisted.conch import manhole, manhole_ssh
from twisted.scripts import twistd
import utils
import unicast_manager
# from udp_server_manage import udp_reader_process

sys.path.insert(0, os.getcwd())

config = utils.config


# as per twisted 15.0.0
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


# for twisted > 17.1.0
# def getManholeFactory(namespace, **passwords):
#     checker = checkers.InMemoryUsernamePasswordDatabaseDontUse(**passwords)
#
#     def getMahole(arg):
#         return manhole.ColoredManhole(namespace)
#
#     realm = manhole_ssh.TerminalRealm()
#
#     realm.chainedProtocolFactory.protocolFactory = getMahole
#     p = portal.Portal(realm, [checker])
#     # p.registerChecker(
#     #     )
#     f = manhole_ssh.ConchFactory(p)
#     f.publicKeys[b'ssh-rsa'] = keys.Key.fromFile("/home/deepen/Documents/deepen/key/deepen.pub")
#     f.privateKeys[b'ssh-rsa'] = keys.Key.fromFile("/home/deepen/Documents/deepen/key/deepen")
#     return f


log = utils.get_logger("speech")
observer = PythonLoggingObserver("speech")
observer.start()

manhole_service = internet.TCPServer(2024,
                                     getManholeFactory(globals(), admin='a&b'))
mainService = service.MultiService()
mainService.setName("speech")
mainService.addService(unicast_manager.main())

application = service.Application("speech")
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


# start udp reader spawn process
# udp_reader_process()
unicast_manager.udp_reader_process()

twistd._SomeApplicationRunner = ApplicationRunner
# import profile
# profile.run(twistd.run())
twistd.run()
