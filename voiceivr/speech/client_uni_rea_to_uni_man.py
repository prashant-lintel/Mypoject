from twisted.internet.protocol import ClientCreator
from twisted.internet import reactor
import utils
import jsonnode
import time

# HOST = '127.0.0.1'
PORT = 2001
config = utils.config
log = utils.get_logger('client_uni_rea_to_uni_man')


class ClientProtocol(jsonnode.NodeClientProtocol):
    """
    Client Protocol.
    """
    def __init__(self, args=None):
        self.args = args
        self.port = None
        self.udp_receiver_object = None

    def curtum_speech_transcribe(self, call_uuid=None, udp_port=None, speech_data=None):
        log.debug(' Receive Command "uni_man_speech_transcribe"')
        msg = jsonnode.NodeMessage()
        msg['msg'] = None
        msg["timestamp"] = time.time()
        msg["msg-uuid"] = utils.getUUID()
        msg['command'] = 'uni_man_speech_transcribe'
        msg['call_uuid'] = call_uuid
        msg['speech_data'] = speech_data
        msg['udp_port'] = udp_port
        # msg = {}
        df = self.sendCommand(msg)
        df.addCallback(self.command_success_respone)
        df.addErrback(self.command_error_response)
        self.transport.loseConnection()
        return df

    def command_success_respone(self, suc):
        """
        sendcommand success callback.
        :param suc: defer argument.
        :return: defer callback.
        """
        log.debug("Command success : %s" % suc)
        return suc

    def command_error_response(self, er):
        """
        sendcommand error callback.
        :param er: defer argument.
        :return: defer callback.
        """
        log.error('Command fail : %s' % er)
        return er


def client_connect_success(suc, call_uuid=None, udp_port=None, speech_data=None):
    """
    Client success callback.
    :param suc: defer argument.
    :param call_uuid: call uuid.
    :param udp_port: udp port.
    :param speech_data: speech data.
    :return: defer callback.
    """
    log.debug('client connected : %s' % suc)
    return suc.curtum_speech_transcribe(call_uuid=call_uuid, udp_port=udp_port, speech_data=speech_data)


def client_connect_error(er):
    """
    Client error callback.
    :param er: defer argument.
    :return: defer callback.
    """
    log.error('client not connected : %s' % er)
    return er


def connect_client_unicast_man_to_uni_rea(call_uuid=None, udp_port=None, speech_data=None):
    """
    It is connect client unicast manager to unicast reader.
    :param call_uuid: call uuid.
    :param udp_port: udp port.
    :param speech_data: speech data.
    :return: defer callback.
    """
    global PORT
    cc = ClientCreator(reactor, ClientProtocol)
    df = cc.connectTCP(config.get('speech', 'host'), PORT)
    df.addCallback(client_connect_success, call_uuid=call_uuid, udp_port=udp_port, speech_data=speech_data)
    df.addErrback(client_connect_error)
    return df
