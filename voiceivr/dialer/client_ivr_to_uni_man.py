from twisted.internet import protocol, reactor
from twisted.internet.protocol import ClientCreator
import utils
import jsonnode
import time

HOST = '127.0.0.1'
PORT = 2001

config = utils.config
log = utils.get_logger('client_ivr_to_uni_man')


class ClientProtocol(jsonnode.NodeClientProtocol):
    def __init__(self, args=None):
        self.args = args
        self.port = None

    def get_free_port(self, call_uuid=None, udp_port=None):
        # Something like this
        msg = jsonnode.NodeMessage()
        msg['msg'] = None
        msg["timestamp"] = time.time()
        msg["msg-uuid"] = utils.getUUID()
        msg['command'] = 'get_free_port'
        msg['call_uuid'] = call_uuid
        msg['udp_port'] = udp_port
        # msg = {}
        df = self.sendCommand(msg)
        df.addCallback(self.command_success_respone)
        df.addErrback(self.command_error_response)
        return df

    def command_success_respone(self, suc):
        log.debug('Success response : %s' % suc)
        return suc

    def command_error_response(self, er):
        log.error('Error response : %s' % er)
        return er


def client_connect_success(suc, call_uuid=None):
    log.debug('Client connected : %s' % suc)
    return suc.get_free_port(call_uuid=call_uuid)


def client_connect_fail(er):
    log.error("Client can't connect : %s" % er)
    # connect_client_unicast_man_to_uni_rea()
    return er


def connect_client_ivt_to_uni_main(call_uuid=None):
    global HOST, PORT
    cc = ClientCreator(reactor, ClientProtocol)
    df = cc.connectTCP(HOST, PORT)
    df.addCallback(client_connect_success, call_uuid=call_uuid)
    df.addErrback(client_connect_fail)
    return df
