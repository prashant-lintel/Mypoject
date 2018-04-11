#!/usr/bin/env python2.7
import json
from twisted.internet.defer import Deferred
from twisted.internet.protocol import DatagramProtocol, Protocol, Factory
from twisted.internet import reactor, defer
from twisted.web.iweb import IBodyProducer
from zope.interface import implements
from speech_api import RestSpeechAPI
import base64

REACTOR_OBJECT = None


def sendTranscribeToIVR(data=None, port=None):
    print ('\nProcessing for send speech transcribe data : %s' % data)

    def onIVRClient(result, data=None):
        print('Client successful : %s' % result)
        # reactor.stop()

    def errIVRClient(error):
        print('Error : %s' % error)
        # reactor.stop()

    # import client
    # df = client.start_client(data=data, port=port)
    # df.addCallback(onIVRClient, data=data)
    # df.addErrback(errIVRClient)


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
    def __init__(self, finished, protocol=None):
        self.finished = finished
        self.remaining = 1024 * 10
        self.protocol = protocol

    def dataReceived(self, bytes):
        if self.remaining:
            display = bytes[:self.remaining]
            try:
                a = json.loads(display)
                b = a['results'][0]['alternatives'][0]['transcript']
                print('Final Data : %s' % b)
                # sendTranscribeToIVR(data=b, port=self.port)
                self.protocol.speech_transcribed(b)
            except Exception as e:
                print('Error : %s' % e)
                self.protocol.speech_transcribed('nothing')
                # return defer.fail({'msg': 'nothing'})
            self.remaining -= len(display)
            # print('after speech transcribe : %s' % datetime.datetime.now())
            return defer.succeed('speech transcribed')


def stop_fs_receiver(protocol=None):
    print('reactor call later function called.')
    # sendTranscribeToIVR('nothing', port=port)
    global REACTOR_OBJECT
    REACTOR_OBJECT.stopListening()
    protocol.speech_transcribed('nothing')


class UnicastUDP(DatagramProtocol):
    buf = []
    requests = []

    def __init__(self, protocol=None):
        self.speech_trans = ""
        # self.port = port
        self.protocol = protocol

    def datagramReceived(self, data, (host, port)):
        self.buf.append(data)
        if len(self.buf) > 100:
            data = ''.join(self.buf)
            self.buf = []
        else:
            return
        print "Received from %s - %s" % (host, port)
        # global REACTOR_OBJECT
        # REACTOR_OBJECT.cancel()
        # print('before call speech api : %s' % datetime.datetime.now())
        j = RestSpeechAPI()
        sc = j.start_process(base64.b64encode(data))
        sc.addCallback(self.sucCallback)
        sc.addErrback(self.errCallback)
        # print('after call speech api : %s' % datetime.datetime.now())
        reactor.callLater(3, stop_fs_receiver, protocol=self.protocol)

        # print('after call speech api : %s' % datetime.datetime.now())

        self.requests = []

    def sucCallback(self, response=None):
        finished = Deferred()
        response.deliverBody(BeginningPrinter(finished, protocol=self.protocol))
        return response

    def errCallback(self, args=None):
        print('error callback : %s' % args)
        return args


def start_fs_receiver(port=None, protocol=None):
    print('starting udp receiver in audio receiver : %s and %s' % (port, protocol))
    global REACTOR_OBJECT
    if port:
        REACTOR_OBJECT = reactor.listenUDP(int(port), UnicastUDP(protocol=protocol))
        # reactor.run()
        return REACTOR_OBJECT
        # pass
    else:
        print('port not found to start service.')


# if __name__ == "__main__":
#     start_fs_receiver(port=sys.argv[1])
