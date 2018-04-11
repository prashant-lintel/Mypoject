#!/usr/bin/env python2.7
import time
from twisted.internet import reactor, protocol, defer
from twisted.internet.defer import Deferred
from twisted.internet.protocol import DatagramProtocol, Protocol
import jsonnode
import utils
from twisted.web.iweb import IBodyProducer
from zope.interface import implements
import sys
import subprocess
import json
from client_uni_rea_to_uni_man import connect_client_unicast_man_to_uni_rea
from speech_api import RestSpeechAPI
import base64

log = None
BASE_PORT = None
MAX_SESSIONS = None
config = utils.config


class StringProducer(object):
    implements(IBodyProducer)

    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return defer.succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass
# print credentials


class BeginningPrinter(Protocol):
    def __init__(self, finished, protocol=None, port=None):
        self.finished = finished
        self.remaining = 1024 * 10
        self.protocol = protocol
        self.port = port

    def dataReceived(self, bytes):
        if self.remaining:
            display = bytes[:self.remaining]
            try:
                a = json.loads(display)
                b = a['results'][0]['alternatives'][0]['transcript']
                log.debug('Final Data : %s for port : %s' % (b, self.port))
                # sendTranscribeToIVR(data=b, port=self.port)
                self.protocol.stop_udp_receiver(b, port=self.port)
            except Exception as e:
                print('Error : %s' % e)
                self.protocol.stop_udp_receiver('nothing', port=self.port)
                # return defer.fail({'msg': 'nothing'})
            self.remaining -= len(display)
            # print('after speech transcribe : %s' % datetime.datetime.now())
            return defer.succeed('speech transcribed')


class UnicastUDP(DatagramProtocol):
    """
    UDP Datagram protocol.
    """
    # buf = []
    # requests = []

    def __init__(self, uni_reader=None):
        self.speech_trans = ""
        self.port = None
        self.protocol = uni_reader
        self.buf = []
        self.requests = []
        self.j = RestSpeechAPI()
        # reactor.callLater(3, self.protocol.stop_udp_receiver, data='nothing')

    def datagramReceived(self, data, (host, port)):
        """
        It receives audio chunk data.
        """
        # log.info('starting to receive data.')
        # reactor.callLater(3, self.protocol.stop_udp_receiver)
        self.buf.append(data)
        if len(self.buf) > 100:
            data = ''.join(self.buf)
            self.buf = []
        else:
            return
        reactor.callLater(config.getint('speech', 'seconds_to_stop_receiver_audio'), self.protocol.stop_udp_receiver,
                          data='nothing', port=port)
        log.info("Received from %s - %s" % (host, port))
        self.port = port
        # j = RestSpeechAPI()
        sc = self.j.start_process(base64.b64encode(data))
        sc.addCallback(self.sucCallback)
        sc.addErrback(self.errCallback)
        self.buf = []
        self.requests = []

    def sucCallback(self, response=None):
        """
        Success callback for speech object.
        :param response: defer argument.
        :return: defer callback.
        """
        finished = Deferred()
        response.deliverBody(BeginningPrinter(finished, protocol=self.protocol, port=self.port))
        return response

    def errCallback(self, args=None):
        """
        Error callback for speech object.
        :param args: defer argument.
        :return: defer callback.
        """
        print('error callback : %s' % args)
        return args


class UnicastReaderProtocol(jsonnode.NodeServerProtocol, object):
    """
    Unicast Reader program protocol.
    """

    def __init__(self, factory):
        super(UnicastReaderProtocol, self).__init__()
        self.users = factory.users
        self.last_port_use = factory.last_port_use
        self.udp_receiver_object = None
        self.call_uuid = None
        self.speech_data_send = False

    def connectionLost(self, reason):
        super(UnicastReaderProtocol, self).connectionLost(reason)
        log.debug('Total users : %s' % self.users)
        self.users -= 1
        log.debug('Total users : %s' % self.users)

    @jsonnode.command("check_port")
    def send_udp_port(self, event):
        log.debug('Receive Command "check_port" : %s' % event)
        msg = jsonnode.NodeMessage()
        msg["timestamp"] = time.time()
        msg["msg"] = "Reply >> %s" % event["msg"]
        # msg["Reply-Text"] = "+OK"
        msg["msg-uuid"] = event["msg-uuid"]
        msg['call_uuid'] = event['call_uuid']
        self.call_uuid = event['call_uuid']
        msg['udp_port'] = event['udp_port']
        # self.sendCommandReply(msg)
        global MAX_SESSIONS
        if self.users >= MAX_SESSIONS:
        # if True:
            msg["Reply-Text"] = "- ERR"
            self.sendCommandReply(msg)
            # self.transport.loseConnection()
            log.error('Reactor will stop.')
            reactor.callLater(2, reactor.stop)
        else:
            msg["Reply-Text"] = "+OK"
            port = self.check_port_available()
            if port:
                msg['udp_port'] = port
            else:
                log.error('Port not found.')
                msg['udp_port'] = None
        if self.start_udp_receiver(udp_port=port):
            self.sendCommandReply(msg)
        else:
            log.error('udp port not able to start')
            msg["Reply-Text"] = "- ERR"
            self.sendCommandReply(msg)
        # self.start_udp_receiver(udp_port=port)
        self.transport.loseConnection()

    def check_port_available(self):
        """
        It's check process runs on specific port or not.
        :return: if process does not run on port. it returns port number. otherwise False(boolean).
        """
        global BASE_PORT
        BASE_PORT += 1
        cmd = 'netstat -lntup | grep %s' % BASE_PORT
        for i in range(5):
            try:
                a = subprocess.check_output(cmd, shell=True)
                log.debug('process runs on port : %s and info: %s' % (BASE_PORT, a))
                # return False
            except Exception as e:
                log.debug('process does not run on port : %s' % BASE_PORT)
                return BASE_PORT
        return False

    def start_udp_receiver(self, udp_port=None):
        """
        It starts listen on port for udp.
        :param udp_port: port number.
        :return: boolean value.
        """
        log.info('start udp listen on %s' % udp_port)
        if udp_port:
            self.users += 1
            self.udp_receiver_object = reactor.listenUDP(int(udp_port), UnicastUDP(self))
            reactor.callLater(config.getint('speech', 'seconds_to_stop_receiver_audio') + 5,
                              self.check_port_not_running, port=udp_port)
            self.speech_data_send = False
            # reactor.callLater(4, self.stop_udp_receiver, data='nothing')
            return True
        else:
            log.error('Port number not found to start udp listening.')
            return False

    def stop_udp_receiver(self, data=None, port=None):
        """
        It's stop listens on udp port.
        :param data: speech transcribe data.
        :return: None
        """
        if not self.speech_data_send:
            self.speech_data_send = True
            log.debug('stopping listen on port (UDP) : %s' % port)
            self.udp_receiver_object.stopListening()
            connect_client_unicast_man_to_uni_rea(call_uuid=self.call_uuid, udp_port=self.last_port_use,
                                                  speech_data=data)
        else:
            log.debug('Already speech processed')

    def check_port_not_running(self, port=None):
        """
        It checks for process running on port or not.
        It used for if port automatically not close in system.
        :param port: port number
        :return: None
        """
        log.debug('call later function to check process run on used port : %s' % port)
        cmd = 'netstat -lntup | grep %s' % int(port)
        try:
            a = subprocess.check_output(cmd, shell=True)
            log.debug('process runs on port : %s and info: %s' % (port, a))
            self.udp_receiver_object.stopListening()
        except Exception as e:
            log.debug('process does not run on port : %s' % port)


class UnicastReaderFactory(protocol.ServerFactory):
    protocol = UnicastReaderProtocol

    def __init__(self):
        # use can add another variable to maintain user list.
        self.users = 0
        self.last_port_use = 0

    def buildProtocol(self, addr):
        p = self.protocol(self)
        p.factory = self
        return p


def main(port=None, base_port=None):
    """
    It starts listen on received port.
    :param port: port number
    :param base_port: base porn number to start another listen process for udp.
    :return: None
    """
    factory = UnicastReaderFactory()
    global log, BASE_PORT, MAX_SESSIONS, config
    BASE_PORT = int(base_port)
    MAX_SESSIONS = config.getint('speech', 'max_sessions')
    log = utils.get_logger('unicast_reader_%s' % port)
    log.info('Unicast Reader starts on : %s' % port)
    s = reactor.listenTCP(int(port), factory)
    reactor.run()
    # return s


if __name__ == "__main__":
    # print(sys.argv)
    main(sys.argv[1], sys.argv[2])
