#!/usr/bin/env python2.7
import time
from twisted.application import internet
from twisted.internet import reactor, protocol, defer
import jsonnode
import utils

# config = utils.config
log = utils.get_logger('spawn_server')


class JsonServerProtocol(jsonnode.NodeServerProtocol, object):

    def __init__(self, dialer):
        self.dialer = dialer
        super(JsonServerProtocol, self).__init__()
        self.udp_server_object = None
        self.msg = None

    @jsonnode.command("speech_transcribe")
    def speech_transcribe(self, event):
        log.debug(' Received command "speech_transcribe" : %s' % event)
        msg = jsonnode.NodeMessage()
        msg["timestamp"] = time.time()
        msg["msg"] = "Reply >> %s" % event["msg"]
        msg["Reply-Text"] = "+OK"
        msg["msg-uuid"] = event["msg-uuid"]
        msg['call_uuid'] = event['call_uuid']
        msg['udp_port'] = event['udp_port']
        msg['speech_data'] = event['speech_data']
        self.sendCommandReply(msg)
        self.speech_transcribed(call_uuid=event['call_uuid'], msg=event['speech_data'])

    def speech_transcribed(self, call_uuid=None, msg=None):
        # self.dialer.speech_transcribed_data[call_uuid] = msg
        try:
            call_obj = self.dialer.inbound_calls_dialer_reference[call_uuid]
            log.debug('Call object retrieving for uuid : %s and object id : %s' % (call_uuid, call_obj))
            call_obj.call_listen.after_speech_transcribe_unicast(data=msg)
        except Exception as e:
            log.error('error while call object fetch')
            print(e)


class JsonServerFactory(protocol.ServerFactory):
    protocol = JsonServerProtocol

    def __init__(self, dialer):
        # use can add another variable to maintain user list.
        self.users = {}
        self.dialer = dialer

    def buildProtocol(self, addr):
        p = self.protocol(self.dialer)
        p.factory = self
        return p


def main(dialer):
    factory = JsonServerFactory(dialer)
    s = internet.TCPServer(2000, factory)
    # reactor.run()
    return s


if __name__ == "__main__":
    import sys
    log.debug(sys.argv)
    main(sys.argv[1])
