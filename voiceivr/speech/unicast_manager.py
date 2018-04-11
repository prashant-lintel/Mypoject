#!/usr/bin/env python2.7
import time
from twisted.internet import protocol, reactor, defer
from twisted.internet.protocol import ClientCreator
import jsonnode
import utils
from twisted.application import internet
import os

config = utils.config
log = utils.get_logger('unicast_manager')


TOTAL_UDP_SERVER = []
NUMBER_OF_TRY = 0
BASE_PORT = {}
# HOST_TO_CONNECT = '127.0.0.1'
generator = None


def robin():
    """
    It is used to use allocate same load on all udp reader programs.
    :return: Port number
    """
    global generator, TOTAL_UDP_SERVER
    generator = (i for i in TOTAL_UDP_SERVER)
    final_data = generator.next()
    TOTAL_UDP_SERVER.pop(0)
    TOTAL_UDP_SERVER.append(final_data)
    # print(TOTAL_UDP_SERVER)
    # print(type(final_data))
    log.debug('udp reader goes to use : %s' % final_data)
    return final_data


def start_spawn_process(port=None, base_port=None):
    """
    It's start spawn process on different ports for receive audio from freeswitch.

    :param : base_port
    :return: None
    """
    if port and base_port:
        # unicast_reader = '/home/deepen/Documents/voiceivr/speech/unicast_reader.py'
        unicast_reader = config.get('speech', 'unicast_reader_file_path')
        args = [unicast_reader, str(port), str(base_port)]
        reactor.spawnProcess(None, unicast_reader, args, env=os.environ, childFDs={0: 0, 1: 1, 2: 2}, )
    else:
        log.error('port not passed.')


def udp_reader_process():
    """
    It fetches number of ports to start from config file and start spawn process.
    :return: None
    """
    number_of_process = config.getint('speech', 'process_to_start')
    global TOTAL_UDP_SERVER, BASE_PORT
    if number_of_process != 0:
        for i in range(number_of_process):
            server_port = config.getint('speech_spawn', 'server_%s' % i)
            TOTAL_UDP_SERVER.append(server_port)
            base_port = config.getint('speech_spawn', 'server_base_port_%s' % i)
            BASE_PORT[server_port] = base_port
            start_spawn_process(port=server_port, base_port=base_port)
        # start_spawn_process()
    else:
        log.error('Number of process to start is not defined. \n Please, once define in speech.conf file.')

    # for i in range(number_of_process):
    #     robin()


class ClientProtocol(jsonnode.NodeClientProtocol):
    """
    It's a used for connect client.
    """
    def __init__(self, args=None):
        self.args = args
        self.port = None
        self.udp_receiver_object = None

    def check_port(self, call_uuid=None, udp_port=None):
        """
        It send command check_port to unicast reader program from unicast manager.
        :param call_uuid: call uuid.
        :param udp_port: port number.
        :return: defer callback.
        """
        log.debug(' Send Command "check_port" for call uuid : %s' % call_uuid)
        msg = jsonnode.NodeMessage()
        msg['msg'] = None
        msg["timestamp"] = time.time()
        msg["msg-uuid"] = utils.getUUID()
        msg['command'] = 'check_port'
        msg['call_uuid'] = call_uuid
        msg['udp_port'] = udp_port
        # msg = {}
        df = self.sendCommand(msg)
        df.addCallback(self.command_success_respone)
        df.addErrback(self.command_error_response)
        return df

    def uni_man_client_protocol_speech_transcribe(self, event=None, call_uuid=None, udp_port=None, speech_data=None):
        """
        It is send command unicast manager to ivr program.
        :param event: jsonnode message.
        :param call_uuid: call uuid.
        :param udp_port: udp port.
        :param speech_data: speech transcribed message.
        :return: defer callback.
        """
        log.debug(' Send Command "speech_transcribe" : %s' % event)
        msg = jsonnode.NodeMessage()
        msg["timestamp"] = time.time()
        msg["msg"] = "Reply >> speech transcribe"
        msg["Reply-Text"] = "+OK"
        msg["msg-uuid"] = utils.getUUID()
        msg['call_uuid'] = event['call_uuid']
        msg['udp_port'] = event['udp_port']
        msg['command'] = 'speech_transcribe'
        msg['speech_data'] = event['speech_data']
        # msg = {}
        df = self.sendCommand(msg)
        df.addCallback(self.command_success_respone)
        df.addErrback(self.command_error_response)
        self.transport.loseConnection()
        return df

    def command_success_respone(self, suc):
        """
        It's success callback for sendcommand.
        :param suc: defer argument.
        :return: defer callback.
        """
        log.debug("Command success : %s" % suc)
        # TODO: check response if err not contain in message data.
        try:
            if suc['Reply-Text'] == '- ERR':
                log.error('Error captured while udp port received.')
                return defer.fail({'error': 'error captured while udp port received'})
            else:
                pass
        except Exception as e:
            log.error('Exception captured at udp port received.')
            print(e)
        return suc

    def command_error_response(self, er):
        """
        It's error callback for sendcommand.
        :param er: defer argument.
        :return: defer callback.
        """
        log.error('Command fail : %s' % er)
        # try:
        #     if er['Reply-Text'] == '- ERR':
        #         log.error('Error captured while udp port received.')
        #         return defer.fail({'error': 'error captured while udp port received'})
        #     else:
        #         pass
        # except Exception as e:
        #     print('Exception captured at udp port received.')
        #     print(e)
        return er


class UnicastManagerProtocol(jsonnode.NodeServerProtocol, object):
    """
    Handles udp port management.
    Check udp port and start listening on that port.
    """

    def __init__(self):
        super(UnicastManagerProtocol, self).__init__()
        self.udp_server_object = None
        self.msg = None
        self.call_uuid = None
        self.udp_port = None
        self.counter = 0

    def client_connect_success(self, suc=None, speech_transcribed=None, msg=None, port=None):
        """
        It is generalized success callback for client connection.
        :param suc: general defer argument.
        :param speech_transcribed: It is boolean value. If it's true, then send speech transcribed to ivr program.
        :param msg: jsonnode message.
        :param port: port number.
        :return: defer callbacks.
        """
        log.debug('Client connected : %s' % suc)
        if speech_transcribed:
            suc.uni_man_client_protocol_speech_transcribe(event=msg)
            return defer.succeed('speech transcribed message send.')
        df = suc.check_port(call_uuid=self.call_uuid, udp_port=self.udp_port)
        df.addCallback(self.received_command_reply_success)
        df.addErrback(self.received_command_reply_error, call_uuid=self.call_uuid, port=port)
        df.addBoth(self.connection_close_after_use, send_port=True)
        return df

    def client_connect_fail(self, er, cumti=None, cumtr=None, port=None):
        """
        It is generalized error callback for client connection.
        :param er: general defer argument.
        :param cumti: It is boolean value and it's described for  client of unicast manager to unicast ivr.
        :param cumtr: Its is boolean value and it's described for client of unicast manager to unicast reader.
        :param port: port number.
        :return: defer callback.
        """
        log.error("Client can't connect : %s" % er)
        if cumtr:
            self.check_process_status(port=port)
            return self.connect_client_unicast_man_to_uni_rea()
        else:
            print('General error callback.')
        return er

    def check_process_status(self, port=None):
        """
        It's use for check process is running or not on specific port.
        It process doesn't running on port, it start spawn process on that port.
        :param port: port number.
        :return: None
        """
        cmd = 'netstat -lntup | grep %s' % port
        try:
            import subprocess
            a = subprocess.check_output(cmd, shell=True)
            log.debug('process runs on port : %s and info: %s' % (port, a))
            # return False
        except Exception as e:
            log.debug('process does not run on port : %s' % port)
            # return self.last_port_use
            global BASE_PORT
            if port in BASE_PORT.keys():
                start_spawn_process(port=port, base_port=BASE_PORT[port])
            else:
                log.error('port not found in global base_port')

    def received_command_reply_success(self, suc):
        """
        This success callback use for check_port command.
        unicast manager request to unicast reader for port.
        :param suc: defer argument.
        :return: defer callback.
        """
        log.debug('Received command reply success : %s' % suc)
        # update udp port and message
        self.msg['udp_port'] = suc['udp_port']
        self.msg['msg'] = suc['msg']
        self.sendCommandReply(self.msg)
        return suc

    def received_command_reply_error(self, er, call_uuid=None, port=None):
        """
        This error callback for check_port command.
        unicast manager request to unicast reader for port.
        :param er: defer argument.
        :param call_uuid: call uuid.
        :param port: port number.
        :return: defer callback.
        """
        log.debug('Received command reply error : %s' % er)
        if er.getErrorMessage() == '- ERR':
            log.error('UDP port not received : %s' % call_uuid)
            self.check_process_status(port=port)
            return self.connect_client_unicast_man_to_uni_rea()
            # return
        return er

    def connection_close_after_use(self, suc, send_port=None):
        """
        Nothing usage.
        :param suc:
        :param send_port:
        :return:
        """
        # if send_port:
        #     suc.protocolClass.
        pass

    @jsonnode.command('get_free_port')
    def free_port(self, event):
        log.debug(' Receive Command  "get_free_port" : %s' % event)
        msg = jsonnode.NodeMessage()
        msg["timestamp"] = time.time()
        msg["msg"] = "Reply >> %s" % event["msg"]
        msg["Reply-Text"] = "+OK"
        msg["msg-uuid"] = event["msg-uuid"]
        msg['call_uuid'] = event['call_uuid']
        msg['udp_port'] = self.udp_port
        self.call_uuid = event['call_uuid']
        self.msg = msg
        self.connect_client_unicast_man_to_uni_rea()

    @jsonnode.command('uni_man_speech_transcribe')
    def uni_man_speech_transcribe(self, event):
        log.debug(' Receive Command  "uni_man_speech_transcribe" : %s' % event)
        msg = jsonnode.NodeMessage()
        msg["timestamp"] = time.time()
        msg["msg"] = "Reply >> %s" % event["msg"]
        msg["Reply-Text"] = "+OK"
        msg["msg-uuid"] = event["msg-uuid"]
        msg['call_uuid'] = event['call_uuid']
        msg['udp_port'] = event['udp_port']
        msg['speech_data'] = event['speech_data']
        # msg['port'] = event['port']
        # self.sendCommandReply(msg)
        self.connect_client_unicast_man_to_ivr(msg=msg)

    def connect_client_unicast_man_to_ivr(self, msg=None):
        """
        It connects unicast manager to main ivr program.
        :param msg: jsonnode message.
        :return: defer callbacks of connecttcp.
        """
        cc = ClientCreator(reactor, ClientProtocol)
        df = cc.connectTCP(config.get('speech', 'host'), 2000)
        df.addCallback(self.client_connect_success, speech_transcribed=True, msg=msg)
        # CUMTI = client_unicast_man_to_ivr
        df.addErrback(self.client_connect_fail, cumti=True)
        return df

    def connect_client_unicast_man_to_uni_rea(self):
        """
        It connects unicast manager to unicast reader.
        :return: defer callbacks of connecttcp.
        """
        port = robin()
        cc = ClientCreator(reactor, ClientProtocol)
        # print(dir(cc))
        df = cc.connectTCP(config.get('speech', 'host'), port)
        df.addCallback(self.client_connect_success, port=port)
        # CUMTR = client_unicast_man_to_uni_rea
        df.addErrback(self.client_connect_fail, cumtr=True, port=port)
        return df
        # return df

    # @jsonnode.command("speech_transcribe")
    # def speech_transcribe(self, event):
    #     log.debug('received speech transcribed : %s' % event)
    #     msg = jsonnode.NodeMessage()
    #     msg["timestamp"] = time.time()
    #     msg["msg"] = "Reply >> %s" % event["msg"]
    #     msg["Reply-Text"] = "+OK"
    #     msg["msg-uuid"] = event["msg-uuid"]
    #     msg['port'] = event['port']
    #     self.sendCommandReply(msg)
    #
    # @jsonnode.command("client_connect")
    # def client_connect(self, event):
    #     log.debug('received client request : %s' % event)
    #     # log.debug('Check received events : %s' % event.keys())
    #     log.debug('Check connected : %s' % self.connected)
    #     msg = jsonnode.NodeMessage()
    #     msg["timestamp"] = time.time()
    #     msg["msg"] = "Reply >> %s" % event["msg"]
    #     msg["Reply-Text"] = "+OK"
    #     msg["msg-uuid"] = event["msg-uuid"]
    #     msg['call_uuid'] = event['call_uuid']
    #     msg['udp_port'] = event['udp_port']
    #     msg['speech_transcribed'] = event['speech_transcribed']
    #     # log.debug('message can be sent : %s' % msg)
    #     self.msg = msg
    #     self.start_udp_receiver(port=event['udp_port'], msg=msg)
    #     # self.sendCommandReply(msg)
    #     # log.debug('Check connected after send reply : %s' % self.connected)

    # def start_udp_receiver(self, port, msg=None):
    #     # log.debug('message in start udp receiver : %s' % msg)
    #     # log.debug(dir(self.udp_server_object))
    #     self.udp_server_object = start_fs_receiver(port, protocol=self)
    #     # reactor.callLater(3, self.stop_udp_receiver, msg=msg)
    #
    # def stop_udp_receiver(self, msg=None):
    #     log.debug('After 3 seconds reactor stop.')
    #     # log.debug('message in stop udp receiver : %s' % msg)
    #     # self.udp_server_object.stopListening()
    #     self.speech_transcribed('nothing', msg=msg)
    #
    # def speech_transcribed(self, args=None, msg=None):
    #     # log.debug('speech transcribed received : %s' % args)
    #     # log.debug('message in speech transcribed : %s' % msg)
    #     self.msg['speech_transcribed'] = args
    #     self.sendCommandReply(self.msg)


class UnicastManagerFactory(protocol.ServerFactory):
    protocol = UnicastManagerProtocol

    def __init__(self):
        self.users = {}

    def buildProtocol(self, addr):
        p = self.protocol()
        p.factory = self
        return p


def main():
    """
    Starts tcp server to listening.
    :return: Tcp server instance.
    """
    factory = UnicastManagerFactory()
    s = internet.TCPServer(config.getint('speech', 'port'), factory)
    return s
