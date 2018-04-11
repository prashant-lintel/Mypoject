import logging
import urllib
from twisted.application import internet
from twisted.internet.defer import inlineCallbacks
from pyswitch import outbound
import pyswitch.fsprotocol
from . import utils
from call_listen import CallListenOperation
import txdbinterface as txdb

# for create call object.
from dialer.call import createCallObj

__author__ = 'Deepen Patel'

pyswitch.fsprotocol.log.setLevel(logging.INFO)
pyswitch.fsprotocol.log.setLevel(logging.DEBUG)

config = utils.config
log = utils.get_logger('incoming_call_outbound_socket')


class Action(object):

    def __init__(self, protocol):
        self.protocol = protocol

    def start_command(self, cmd_name, cmd_args):
        log.debug('request received to execute : %s %s' % (cmd_name, cmd_args))
        # df = self.protocol.sendCommand("execute_extension", '1599 XML public', lock=True)
        df = self.protocol.sendCommand(cmd_name, cmd_args, lock=True)
        df.addCallback(self.command_success)
        df.addErrback(self.command_fail)
        return df

    def command_success(self, event):
        log.info('Successfully Command Executed.')
        return event

    def command_fail(self, event):
        log.error('Failed to execute command.')
        log.error(event)
        return event


class IncomingOutbound(outbound.OutboundProtocol, Action, CallListenOperation):
    """
    Outbound socket.
    """

    def __init__(self, dialer):
        self.dialer = dialer
        self.stats = dialer.stats
        self.calls = dialer.calls
        self.inbound_call_info = dict
        self.uuid = str
        self.web_hook_url = str
        self.processed_action_via_digit = False
        self.call_detail_dict = dict
        self.call_bridge_url = str
        self.speech_transcribe_keyword_match = False
        self.speech_transcribe_keyword_data = str
        super(IncomingOutbound, self).__init__(self)
        self.call_listen = CallListenOperation(self)

    def connectComplete(self, call_info):
        """
        After connection established, register events with freeswitch.
        """
        self.uuid = uuid = call_info['Unique-ID']
        log.info('successfully connected to outbound socket(incoming call)......:%s', uuid)
        log.debug("Connected outbound(incoming call). call_info: %s", call_info)
        self.registerEvent('CHANNEL_ANSWER', True, self.channelAnswer)
        self.registerEvent('CHANNEL_HANGUP', True, self.channelHangup)
        self.registerEvent('CHANNEL_HANGUP_COMPLETE', True, self.channelHangupComplete)
        self.registerEvent('CHANNEL_STATE', True, self.channelStatechange)
        self.registerEvent('CHANNEL_PROGRESS', True, self.channelProgress)
        self.registerEvent('CHANNEL_BRIDGE', True, self.channelBridge)
        self.registerEvent('CHANNEL_UNBRIDGE', True, self.channelUnBridge)
        self.registerEvent('DTMF', True, self.channelDTMF)
        self.registerEvent('MENU_ACTION', True, self.handleMenuAction)
        self.myevents()
        self.answer()
        self.inbound_call_info = call_info
        self.call_bridge_url = config.get('fs', 'dial_string')
        self.dialer.incoming_call_outbound_socket = self
        self.dialer.inbound_calls_dialer_reference[uuid] = self
        self.doStart()
        # self.call_listen_start()

    def handleMenuAction(self, event):
        log.debug("EVENT EVENT EVENT  MENU_ACTION  %s", event)
        action = urllib.unquote(event['action'])
        _action = action.split("|")
        args = _action[1:]
        action = _action[0]
        digit = event['digit']
        cb = getattr(self, action, None)
        if callable(cb):
            cb(*args)
        else:
            log.error("No such IVR action %s", action)

    def channelExecuteComplete(self, event):
        if event['Application'] == "play_and_get_digits":
            log.info(
                ":: CHANNEL_EXECUTE_COMPLETE play_and_get_digits :: Call: %s",
                self.inbound_call_info)
            self._captureDigits(event)

    def channelProgress(self, event):
        log.info("event CHANNEL_PROGRESS on %s", self.uuid)

    def channelAnswer(self, event):
        log.debug('Channel answer event : %s' % event)
        log.info("event CHANNEL_ANSWER on %s", self.uuid)

    def channelBridge(self, event):
        log.debug("Channel Bridged on %s", self.uuid)

    def channelUnBridge(self, event):
        log.debug("Channel Un Bridged on %s", self.uuid)
        # self.channel_hangup()
        # return
        
    def channelHangup(self, event):
        log.info("event CHANNEL_HANGUP on %s", self.uuid)

    def channelHangupComplete(self, event):
        log.info("event CHANNEL_HANGUP_COMPLETE on %s", self.uuid)
        self.decrement_call()
        callobj = self.calls.pop(self.uuid)
        # callobj.hangup = True
        self.dialer.inbound_calls_dialer_reference.pop(self.uuid)
        log.info("Popped call object %s", callobj)

        # self.channel_hangup()
        return

    def channelStatechange(self, event):
        pass

    def channelDTMF(self, event):
        uuid = self.uuid
        log.debug("DTMF detected on channel %s", event)
        digit = event['DTMF-Digit']
        try:
            # data = config.get('incoming_call_user_db', digit)
            log.debug('type of digit : %s' % type(digit))
            log.debug(self.call_listen.invalid_respone_count)
            if digit == '0' and self.call_listen.invalid_respone_count == 2:
                self.processed_action_via_digit = True
                log.debug('Digit Detected : %s' % digit)
                self.call_listen.after_invalid_response(digit=digit)
            else:
                log.error('DIGIT : %s' % digit)
                log.error('Entered DIGIT has no action to perform.')
            # elif digit == '1' and self.speech_transcribe_keyword_match:
            #     self.call_bridge_action(digit)

            # if digit in self.call_detail_dict.keys() and not self.processed_action:
            #     self.processed_action = True
            #     log.debug('DTMF : %s and data fetched : %s' % (digit, self.call_detail_dict.get(digit)))
            #     # bridge_url = "sofia/internal/{}%192.168.0.8".format(self.call_detail_dict.get(digit))
            #     self.call_bridge_url = "{absolute_codec_string='PCMA,PCMU'}" + self.call_bridge_url
            #     bridge_url = self.call_bridge_url % self.call_detail_dict.get(digit)
            #     log.debug('Call will be bridge to : {}'.format(bridge_url))
            #     self.start_command('bridge', bridge_url)
            #     self.channel_hangup()
            #     # return
            # else:
            #     log.debug('nothing found with respect to entered digit or already input received through speech.')
        except Exception as e:
            log.error('Error in dtmf : %s' % e)

    # def call_bridge_action(self, digit=None):
    #     try:
    #         if digit == '1' and self.speech_transcribe_keyword_data in self.call_detail_dict.keys() and not self.processed_action:
    #             self.processed_action = True
    #             log.debug('DTMF : %s and data fetched : %s' % (digit, self.call_detail_dict.get(self.speech_transcribe_keyword_data)))
    #             # bridge_url = "sofia/internal/{}%192.168.0.8".format(self.call_detail_dict.get(digit))
    #             self.call_bridge_url = "{absolute_codec_string='PCMA,PCMU'}" + self.call_bridge_url
    #             bridge_url = self.call_bridge_url % self.call_detail_dict.get(digit)
    #             log.debug('Call will be bridge to : {}'.format(bridge_url))
    #             self.start_command('bridge', bridge_url)
    #             self.channel_hangup()
    #         else:
    #             log.error('Entered DTMF not associated with any actions.')
    #     except Exception as e:
    #         log.error('Error in dtmf capture : %s' % e)

    def event_menu_action(self, event):
        uuid = self.uuid
        log.debug("IVR Menu start detect : %s", event)

    def event_menu_exit(self, event):
        log.debug("IVR Menu stop detect : %s" % event)
        
    def event_speech_detection(self, event):
        log.debug('Speech Detection event : %s' % event)

    def increment_call(self):
        self.stats.total_bridged += 1
        self.stats.total_calls += 1
        self.stats.live_bridged += 1

    def decrement_call(self):
        self.stats.live_bridged -= 1

    @inlineCallbacks
    def doStart(self):
        log.debug('Start processing on call')
        try:
            destination_number = self.inbound_call_info['Caller-Destination-Number']
            context = self.inbound_call_info['Channel-Context']
            caller_direction = self.inbound_call_info['Caller-Direction']
            caller_number = self.inbound_call_info['Caller-Orig-Caller-ID-Number']

            # create call object in redis.
            call_obj = createCallObj(ph=caller_number, uuid=self.uuid, action='inbound_call', action_args=None)
            log.debug('Call object created : %s' % call_obj)
            call_obj.web_hook_url = self.web_hook_url
            self.increment_call()
            log.debug('Required Call information context : %s, caller-dire : %s, dest-num : %s' %(context, caller_direction, destination_number))
            self.set_channel_variables(caller_number)
            query = "select * from input_actions inner join ivr on input_actions.ivr_id= ivr.id " \
                    "where ivr.destination_number='%s'" % destination_number
            # query = "select * from input_actions where ivr_id = 1"
            log.debug('Query run to be : %s' % query)
            db_data = yield txdb.execute(query)
            log.debug('Query response : {}'.format(db_data))
            self.call_detail_dict = final_data = self.query_result_to_dict(db_data)
            query_web_hook = "select * from web_hook inner join ivr on web_hook.ivr_id= ivr.id " \
                             "where ivr.destination_number='%s'" % destination_number
            log.debug('Query run to be : %s' % query_web_hook)
            web_hook_db_data = yield txdb.execute(query_web_hook)
            log.debug('Query response : {}'.format(web_hook_db_data))
            if web_hook_db_data:
                self.web_hook_url = web_hook_db_data[0].get('url')
                log.debug('Web hook url : %s' % self.web_hook_url)
            else:
                log.error('web hook url not found.')
                self.web_hook_url = 'nothing found'
            log.debug('Database result convert to dict : %s' % final_data)
            if final_data:
                # self.check_number_and_play_ivr(destination_number)
                df = self.call_listen.start()
                df.addCallback(self.call_response_success, message='call listen start')
                df.addErrback(self.call_response_fail, message='call listen start')
            else:
                log.error('Call not match with required condition to process further.')
                self.channel_hangup()
                return
        except KeyError as e:
            log.error('Error captured at fetch call information : %s' % e)
            self.channel_hangup()
            return
    
    def call_response_success(self, resp, message=None):
        log.info('call response : %s' % resp)
        
    def call_response_fail(self, er, message=None):
        log.error('call response : %s' % er)
        self.channel_hangup()
        return        

    def query_result_to_dict(self, result):
        # result would be in tuple.
        log.debug('Received query to convert dictionary.')
        if result:
            result_dict = {}
            result_dict.update({result[0]['destination_number']: result[0]['greeting_file_to_play']})
            for i in result:
                result_dict.update({i['dtmf_or_speech']: i['transfer_number']})
            return result_dict
        else:
            log.debug('Nothing found.')
            return

    def set_channel_variables(self, caller_number):
        log.debug('Setting Channel Variables.')
        self.set('caller-orig-number', caller_number)
        self.set('set_audio_level', 'write 4')
        self.set('set_audio_level', 'read 4')

    # def check_number_and_play_ivr(self, destination_number):
    #
    #     try:
    #         data = config.get('incoming_call_user_db', 'sounds_file_path')
    #         log.info('Playing Intro message.')
    #         file_path = data + '{}'.format(self.call_detail_dict[destination_number])
    #         log.debug('files to be play : %s' % file_path)
    #         self.playback(file_path, lock=True)
    #         self.start_command('execute_extension', '1599 XML public')
    #     except Exception as e:
    #         log.error('Error captured at check number and play ivr with respect to that number : %s' %e)
    #         self.channel_hangup()
    #         return

    # def call_speech_record(self):
    #     log.debug('Select Call speech record.')

    def call_speech_record_complete(self):
        log.debug('Select Call speech record complete.')
        # api_cmd = 'unicast 127.0.0.1 8025 127.0.0.1 8026 udp'
        # msg = pyswitch.fsprotocol.Event()
        # msg.set_unixfrom("SendMsg")
        # msg['call-command'] = "unicast"
        # msg['local-ip'] = '127.0.0.1'
        # msg['local-port'] = '8025'
        # msg['remote-ip'] = '127.0.0.1'
        # msg['remote-port'] = '8027'
        # msg['transport'] = 'udp'
        # # msg["command"] = "sendmsg"
        # msg['flags'] = 'native'
        # log.debug('Message can be send to fs : %s' % msg)
        # df = self.sendMsg(msg)
        # # df = self.sendAPI(api_cmd)
        # df.addCallback(self.call_response_success, message='unicast')
        # df.addErrback(self.call_response_fail, message='unicast')
        # self.sendCommand(api_cmd, uuid=self.uuid, lock=True)
        # self.start_google_speech_api_defer()
        df = self.call_listen.call_speech_record_complete()
        df.addCallback(self.call_response_success, message='call speech record complete')
        df.addErrback(self.call_response_fail, message='call speech record complete')

    # def start_google_speech_api_defer(self):
    #     df = defer.Deferred()
    #     # print 'defer initialized.'
    #     df.addCallback(self.defer_for_google_speech)
    #     # print 'called speech api.'
    #     df.addCallback(self.google_speech_response)
    #     df.addErrback(self.google_speech_fail)
    #     df.callback('google_speech_api')
    #     return df

    # def defer_for_google_speech(self, data):
    #     print 'defer args : %s' % data
    #     caller_number = self.inbound_call_info['Caller-Orig-Caller-ID-Number']
    #     file_name = '/tmp/%s.wav' % caller_number
    #     log.debug('Recorded file would be saved as : %s' % file_name)
    #     final = transcribe_file(file_name)
    #     return final
    #
    # def google_speech_response(self, resp):
    #     log.debug('Response success : %s' % resp)
    #     speech_transcribe_detected.send(sender=self.google_speech_response,
    #                         uuid=self.uuid, event=resp,
    #                         web_hook_url=self.web_hook_url, speech=resp,
    #                         caller_id=self.inbound_call_info['Caller-Orig-Caller-ID-Number'])
    #     # if resp == '!#':
    #     #     log.debug('Voice does not recognized properly.')
    #     #     file_path = '/home/deepen/Documents/mbfsapi_data/sounds/voicenotrecognized1.wav'
    #     #     self.playback(file_path, '!', lock=True)
    #     #     self.start_google_speech_api_defer()
    #     # else:
    #     #     # TODO : need to perorm action based on response.
    #     #     pass
    #     try:
    #         # data = config.get('incoming_call_user_db', resp['transcript'])
    #         if resp in self.call_detail_dict.keys() and not self.processed_action:
    #             self.processed_action = True
    #             log.debug('voice : %s and data fetched : %s' % (resp, self.call_detail_dict.get(resp)))
    #             # bridge_url = "sofia/internal/{}%192.168.0.8".format(self.call_detail_dict.get(resp))
    #             bridge_url = self.call_bridge_url % self.call_detail_dict.get(resp)
    #             log.debug('Call will be bridge to : {}'.format(bridge_url))
    #             self.start_command('bridge', bridge_url)
    #             # self.channel_hangup()
    #             # return
    #         else:
    #             log.debug('nothing found with respect to entered voice or already entered dtmf.')
    #     except Exception as e:
    #         log.error('Error in voice : %s' % e)

    # def google_speech_fail(self, resp):
    #     log.error('Response fail : %s' % resp)

    def channel_hangup(self):
        self.hangup()
        log.error('Execute Channel hangup.')


class OutboundDialerFactory(outbound.OutboundFactory):
    """
    Setup Factory for connection with freeswitch.
    """
    protocol = IncomingOutbound

    def __init__(self, dialer):
        self.dialer = dialer
        log.debug('creating OutboundFactory instance for incoming calls.....')

    def buildProtocol(self, addr):
        p = self.protocol(self.dialer)
        p.factory = self
        return p


def getService(dialer):
    """
    Setup and return server service.
    """
    f = OutboundDialerFactory(dialer)
    s = internet.TCPServer(config.getint('network', 'incoming_call_outbound_socket'),
                           f)
    return s
