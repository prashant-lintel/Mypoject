from twisted.internet import defer
import utils
# from .signals import speech_transcribe_detected
import pyswitch.fsprotocol
import subprocess


FS_PORT_RANGE = range(15000, 17000)
TWISTED_PORT_RANGE = range(18000, 20000)
FS_PORT_START = 15000
TWISTED_PORT_START = 18000

__author__ = 'Deepen Patel'

config = utils.config
log = utils.get_logger('call_listen')


class Action(object):

    def __init__(self, protocol):
        self.protocol = protocol

    def start_command(self, args=None, cmd_name=None, cmd_args=None):
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


class DefResponseDebug(object):
    def __init__(self, protocol):
        self.protocol = protocol

    def success_response(self, response, message=None):
        log.debug('Response received :: %s : %s ' % (message, response))
        return response

    def fail_response(self, response, message=None):
        log.error('Response received :: %s : %s ' % (message, response))
        return response

    def play_file_general(self, file_name=None, message=None):
        if file_name:
            log.info('Audio can be play :: {0} : {1}'.format(message, file_name))
            # df = self.protocol.playback(file_name)
            df = self.protocol.playbackSync(file_name)
            df.addCallback(self.success_response, message=message)
            df.addErrback(self.fail_response, message=message)
            return df
        else:
            msg = {'response': 'file name not passed'}
            return defer.fail(msg)


class UnicastOperation:
    """
    This class creates one udp receiver and receives audio.
    Then, transcribes speech.
    """

    def __init__(self, call_listen):
        self.audio_receiver = call_listen
        self.udp_timeout_time_object = None

    def start(self, args=None):
        # TODO : start_udp_service --> check_port_loop is not need.
        # use check_port_loop function's behaviour in start_udp_service. so, only one function use.
        df = self.start_udp_service()
        df.addCallback(self.unicast_start)
        # TODO : start_udp_timeout not need. timeout on udp server is maintain/managed in another process.
        # df.addCallback(self.start_udp_timeout)
        # TODO : add error back
        return df

    # def start_udp_timeout(self, args=None):
    #     # self.udp_timeout_time_object = reactor.callLater(20, self.stop_udp_by_timeout)
    #     # self.udp_timeout_time_object = reactor.callLater(3, self.stop_udp_by_timeout)
    #     log.info('start timeout on speech transcribing.')
    #     return defer.succeed('start timeout')

    # def stop_udp_by_timeout(self, args=None):
    #     log.info('session timeout on speech transcribing.')
    #     # TODO : cancel_call_later not need. timeout on udp server is maintain/managed in another process.
    #     df = self.cancel_call_later()
    #     df.addCallback(self.unicast_stop)
    #     # TODO : stop_udp_listening not need. stop listening on udp server is maintain/managed in another process.
    #     df.addCallback(self.stop_udp_listening)
    #     # TODO : after_speech_transcribe_unicast is not need. this function called from another service.
    #     df.addCallback(self.audio_receiver.after_speech_transcribe_unicast)
    #     df.addErrback(self.audio_receiver.protocol.call_response_fail)

    def start_udp_service(self, event=None):
        # return self.check_port_loop()

        global FS_PORT_START, FS_PORT_RANGE
        if FS_PORT_START not in FS_PORT_RANGE:
            FS_PORT_START = 15000
        else:
            log.debug('ports are in range.')
        for i in range(5):
            self.audio_receiver.fs_audio_fetch_port = FS_PORT_START + 1
            FS_PORT_START = self.audio_receiver.fs_audio_fetch_port
            if self.check_port_available(self.audio_receiver.fs_audio_fetch_port):
                log.debug('Port available for unicast from freeswitch.')
                # return defer.succeed('port available')
                break
            else:
                log.error('port not find to start service.')
                # TODO : return defer fail.

        def suc_callback(msg=None):
            log.debug('success in check port loop: %s' % msg)
            self.audio_receiver.udp_audio_receiver_port = msg['udp_port']
            return msg

        def err_callback(msg=None):
            log.error('error : %s' % msg)
            return msg

        try:
            from client_ivr_to_uni_man import connect_client_ivt_to_uni_main
            df = connect_client_ivt_to_uni_main(call_uuid=self.audio_receiver.protocol.uuid)
            df.addCallback(suc_callback)
            df.addErrback(err_callback)
            return df
        except Exception as e:
            log.error('Error captured at checking port')
            log.error(e)

    def stop_udp_service(self):
        # TODO : cancel_call_later not need. timeout on udp server is maintain/managed in another process.
        # df = self.cancel_call_later()
        # df.addCallback(self.unicast_stop)
        # TODO : stop_udp_listening not need. stop listening on udp server is maintain/managed in another process.
        # df.addCallback(self.stop_udp_listening)
        # TODO : add error back
        self.unicast_stop()
        return defer.succeed('stop service')

    # def cancel_call_later(self, arngs=None):
    #     try:
    #         self.udp_timeout_time_object.cancel()
    #         log.debug('cancel calllater.')
    #     except Exception as e:
    #         log.error('Error occured at cancel calllater function.')
    #         log.error(e)
    #     return defer.succeed('cancel calllater function.')

    # # TODO : delay_call_later is not using.
    # def delay_call_later(self, args=None):
    #     try:
    #         self.udp_timeout_time_object.delay(15)
    #         log.debug('delay calllater.')
    #     except Exception as e:
    #         log.error('Error occured at delay calllater function.')
    #         log.error(e)
    #     return defer.succeed('delay calllater function.')

    # def stop_udp_listening(self, args=None):
    #     try:
    #         self.audio_receiver.udp_service_object.stopListening()
    #         log.debug('UDP service stopped listening for speech transcrie.')
    #     except Exception as e:
    #         log.error('Error occured at stop udp service')
    #         log.error(e)
    #     return defer.succeed('stop service')

    def unicast_start(self, args=None):
        self.audio_receiver.speech_transcribe_processing = False
        msg = pyswitch.fsprotocol.Event()
        msg.set_unixfrom("SendMsg")
        msg['call-command'] = "unicast"
        msg['local-ip'] = '127.0.0.1'
        msg['local-port'] = self.audio_receiver.fs_audio_fetch_port  # '15001'
        msg['remote-ip'] = '127.0.0.1'
        msg['remote-port'] = self.audio_receiver.udp_audio_receiver_port
        msg['transport'] = 'udp'
        log.debug('Message can be send to fs : %s' % msg)
        df = self.audio_receiver.protocol.sendMsg(msg)
        df.addCallback(self.audio_receiver.def_responses.success_response, message='unicast')
        df.addErrback(self.audio_receiver.def_responses.fail_response, message='unicast')
        return df

    def unicast_stop(self, args=None):
        msg = pyswitch.fsprotocol.Event()
        msg.set_unixfrom("SendMsg")
        msg['call-command'] = "stopunicast"
        log.debug('Message can be send to fs : %s' % msg)
        df = self.audio_receiver.protocol.sendMsg(msg)
        df.addCallback(self.audio_receiver.def_responses.success_response, message='stop unicast')
        df.addErrback(self.audio_receiver.def_responses.fail_response, message='stop unicast')
        return df

    def check_port_available(self, port_number=None):
        cmd = 'netstat -lntup | grep %s' % port_number
        try:
            a = subprocess.check_output(cmd, shell=True)
            log.debug('process runs on port : %s and info: %s' % (port_number, a))
            return False
        except Exception as e:
            log.debug('process does not run on port : %s' % port_number)
            return True

    # def check_port_loop(self, args=None):
    #     global FS_PORT_START, FS_PORT_RANGE
    #     if FS_PORT_START not in FS_PORT_RANGE:
    #         FS_PORT_START = 15000
    #     else:
    #         log.debug('ports are in range.')
    #     for i in range(5):
    #         self.audio_receiver.fs_audio_fetch_port = FS_PORT_START + 1
    #         FS_PORT_START = self.audio_receiver.fs_audio_fetch_port
    #         if self.check_port_available(self.audio_receiver.fs_audio_fetch_port):
    #             log.debug('Port available for unicast from freeswitch.')
    #             # return defer.succeed('port available')
    #         else:
    #             log.error('port not find to start service.')
    #             # TODO : return defer fail.
    #
    #     def suc_callback(msg=None):
    #         log.debug('success in check port loop: %s' % msg)
    #         # self.audio_receiver.fs_audio_fetch_port = msg['fs_port']
    #         self.audio_receiver.udp_audio_receiver_port = msg['udp_port']
    #         return msg
    #
    #     def err_callback(msg=None):
    #         log.error('error : %s' % msg)
    #         return msg
    #     # print('check port loop method : %s' % dir(self.audio_receiver.protocol))
    #     # print(self.audio_receiver.protocol.uuid)
    #     try:
    #         # from dialer.speech_spawn.udp_server_manage import send_free_port
    #         # from dialer.udp_server_manage import send_free_port
    #         # data = send_free_port(self.audio_receiver.protocol.uuid, call_object=self)
    #         # data.addCallback(suc_callback)
    #         # data.addErrback(err_callback)
    #
    #         # data = yield send_free_port(self.audio_receiver.protocol.uuid)
    #         # log.debug('received data : %s' % data)
    #         # return data
    #         # log.debug('received port details : %s' % data)
    #         # self.audio_receiver.fs_audio_fetch_port = data['fs_port']
    #         # self.audio_receiver.udp_audio_receiver_port = data['udp_port']
    #         # log.debug('Ports available : %s' % data)
    #         # if data:
    #         #     return defer.succeed('succeed')
    #         # else:
    #         #     return defer.fail({'response': 'port not available.'})
    #         # return defer.succeed('succeed')
    #         # return data
    #         # return returnValue(data)
    #
    #         from client_ivr_to_uni_man import connect_client_ivt_to_uni_main
    #         df = connect_client_ivt_to_uni_main(call_uuid=self.audio_receiver.protocol.uuid)
    #         df.addCallback(suc_callback)
    #         df.addErrback(err_callback)
    #         # self.audio_receiver.fs_audio_fetch_port = 15001
    #         # self.audio_receiver.udp_audio_receiver_port = 18001
    #         # return defer.succeed('succeed')
    #         return df
    #     except Exception as e:
    #         log.error('Error captured at checking port')
    #         log.error(e)

    def speech_receive_in_call_listen(self, args=None):
        log.debug('speech receive in call listen : %s' % args)
        # print(args['speech_transcribed'])
        # self.after_speech_transcribe_unicast()
        self.audio_receiver.after_speech_transcribe_unicast(data=args['speech_transcribed'])


class CallListenOperation(object):

    def __init__(self, protocol):
        global FS_PORT_START
        self.protocol = protocol
        self.no_response_count = 0
        self.invalid_respone_count = 0
        self.no_response_file_number = 2
        self.invalid_response_file_numbr = 5
        self.keyword_heard = False
        self.keyword_heard_speech_not_detected = False
        self.pre_connection_question_bool = False
        self.fs_audio_fetch_port = int
        self.udp_audio_receiver_port = int
        self.sounds_file_path = config.get('incoming_call_user_db', 'sounds_file_path')
        self.action = Action(self.protocol)
        self.unicast_object = UnicastOperation(self)
        self.def_responses = DefResponseDebug(self.protocol)

    def start(self):
        raw_data = """
        Raw data in call listen object
        %s
        """ % self.protocol.call_detail_dict
        log.debug(raw_data)
        df = self.play_intro_message()
        df.addCallback(self.play_say_word_file)
        df.addErrback(self.def_responses.fail_response, message='start')
        return df

    def speech_transcribe_decision(self, args=None, data=None):
        log.debug('Speech transcribe data : %s' % data)
        if self.keyword_heard and not data:
            return self.after_keyword_speech_not_detected()
        if self.keyword_heard:
            self.keyword_heard = False
            df = self.after_keyword_heard(data)
            df.addCallback(self.play_yes_response)
            df.addCallback(self.play_pre_connection_question)
            df.addCallback(self.record_keyword)
            # df.addCallback(self.unicast_object.delay_call_later)
            df.addErrback(self.def_responses.fail_response, message='keyword heard')
            return df
        elif self.pre_connection_question_bool:
            self.pre_connection_question_bool = False
            df = self.after_pre_connecting_question(data)
            df.addCallback(self.action_call_bridge)
            df.addErrback(self.def_responses.fail_response, message='pre condition question played')
            return df
        elif self.invalid_respone_count == 2 and not self.protocol.processed_action_via_digit:
            # df = self.unicast_object.delay_call_later()
            # df.addCallback(self.after_invalid_response, data=data)
            # return df
            return self.after_invalid_response(data=data)
        else:
            df = self.check_speech_trascribed_response(data)
            df.addErrback(self.def_responses.fail_response, message='speech record complete')
            return df

    def after_speech_transcribe_unicast(self, args=None, data=None):
        log.debug('Received speech : %s for %s' % (data, self.udp_audio_receiver_port))
        # df = self.unicast_object.stop_udp_service()
        df = self.unicast_object.unicast_stop()
        df.addCallback(self.speech_transcribe_decision, data=data)
        df.addErrback(self.def_responses.fail_response, message='after speech')
        df.addErrback(self.protocol.call_response_fail)

    def play_intro_message(self):
        file_path = self.sounds_file_path + '{}'.format('DSSD_1_3538_1.wav')
        log.debug('Intro Message played from : %s' % file_path)
        return self.def_responses.play_file_general(file_name=file_path, message='Intro Message')

    def play_say_word_file(self, args=None):
        file_path = self.sounds_file_path + '{}'.format('DSSD_1_3538_2.wav')
        df = self.def_responses.play_file_general(file_name=file_path, message='say keyword')
        df.addCallback(self.record_keyword)
        df.addErrback(self.def_responses.fail_response, message='say keyword')
        return df

    def play_no_response(self, file_name):
        file_path = self.sounds_file_path + '{}'.format(file_name)
        return self.def_responses.play_file_general(file_name=file_path, message='no response')

    def play_invalid_response(self, file_name):
        file_path = self.sounds_file_path + '{}'.format(file_name)
        return self.def_responses.play_file_general(file_name=file_path, message='invalid response')

    def play_keyword_heard(self, args=None):
        # file_path = self.sounds_file_path + '{}'.format('DSSD_1_3538_8.wav')
        # return self.def_responses.play_file_general(file_name=file_path, message='keyword heard')
        command = 'flite|kal|You want ${speech_transcribe_data} correct?'
        return self.action.start_command(cmd_name='speak', cmd_args=command)

    def play_before_bridge_script(self, args=None):
        file_path = self.sounds_file_path + '{}'.format('DSSD_1_3538_11.wav')
        return self.def_responses.play_file_general(file_name=file_path, message='before call bridge script')

    def play_yes_response(self, args=None):
        if self.protocol.speech_transcribe_keyword_data == 'demo':
            file_path = self.sounds_file_path + '{}'.format('DSSD_1_3538_9.wav')
            return self.def_responses.play_file_general(file_name=file_path, message='yes response')
        elif self.protocol.speech_transcribe_keyword_data in ['mb', 'message broadcast']:
            file_path = self.sounds_file_path + '{}'.format('connect_to_mb.wav')
            return self.def_responses.play_file_general(file_name=file_path, message='yes response')
        elif self.protocol.speech_transcribe_keyword_data == 'salem':
            file_path = self.sounds_file_path + '{}'.format('connect_to_salem.wav')
            return self.def_responses.play_file_general(file_name=file_path, message='yes response')
        else:
            command = 'flite|kal|Connecting to ${speech_transcribe_data}'
            return self.action.start_command(cmd_name='speak', cmd_args=command)

    def play_pre_connection_question(self, args=None):
        self.pre_connection_question_bool = True
        file_path = self.sounds_file_path + '{}'.format('DSSD_1_3538_10.wav')
        return self.def_responses.play_file_general(file_name=file_path, message='pre condition question')

    def play_second_time_for_speech_input(self, args=None):
        file_path = self.sounds_file_path + '{}'.format('second_time_ask1.wav')
        return self.def_responses.play_file_general(file_name=file_path, message='second time ask for speech input')

    def play_before_call_bridge(self, args=None):
        file_path = self.sounds_file_path + '{}'.format('play_call_bridge.wav')
        return self.def_responses.play_file_general(file_name=file_path, message='before call bridge')

    def play_speech_transcribing_audio(self, args=None):
        file_path = self.sounds_file_path + '{}'.format('play_speech_ranscribing.wav')
        return self.def_responses.play_file_general(file_name=file_path, message='speech transcribing')

    def play_keyword_confirm_demo(self, args=None):
        file_path = self.sounds_file_path + '{}'.format('demo.wav')
        return self.def_responses.play_file_general(file_name=file_path, message='demo keyword confirm')

    def play_keyword_confirm_mb(self, args=None):
        file_path = self.sounds_file_path + '{}'.format('mb1.wav')
        return self.def_responses.play_file_general(file_name=file_path, message='message broadcast keyword confirm')

    def play_keywork_confirm_salem(self, args=None):
        file_path = self.sounds_file_path + '{}'.format('salem.wav')
        return self.def_responses.play_file_general(file_name=file_path, message='salem keyword confirm')

    def record_keyword(self, args=None):
        log.debug('start call recording dialplan.')
        return self.unicast_object.start()

    def check_speech_trascribed_response(self, response=None):
        log.debug('Received response : %s' % response)
        # speech_transcribe_detected.send(sender=self.check_speech_trascribed_response,
        #                         uuid=self.protocol.uuid, event=response,
        #                         web_hook_url=self.protocol.web_hook_url, speech=response, send_text='',
        #                         caller_id=self.protocol.inbound_call_info['Caller-Orig-Caller-ID-Number'])
        log.debug(self.protocol.call_detail_dict.keys())
        if response:
            if response.endswith('.'):
                response = response[:-1]
            try:
                response = response.lower()
                # if response in self.protocol.call_detail_dict.keys():
                if self.string_check(response):
                    # self.protocol.processed_action = True
                    log.debug('voice : %s and data fetched : %s' % (response,
                                                                    self.protocol.call_detail_dict.get(response)))
                    return self.start_keyword_match()
                else:
                    log.debug('nothing found with respect to entered voice or already entered dtmf.')
                    self.invalid_respone_count += 1
                    self.invalid_response_file_numbr += 1
                    file_name = 'DSSD_1_3538_{}.wav'.format(self.invalid_response_file_numbr)
                    log.debug('Invalid response played : %s' % file_name)
                    if self.invalid_respone_count < 3:
                        # self.play_invalid_response(file_name)
                        # self.record_keyword()
                        df = self.play_invalid_response(file_name)
                        df.addCallback(self.record_keyword)
                        return df
                    else:
                        if self.protocol.processed_action_via_digit:
                            log.debug('Need to continue. because, user has entered dtmf.')
                        else:
                            msg = {'response': 'invalid response timed out'}
                            return defer.fail(msg)
            except Exception as e:
                log.error('Error in voice : %s' % e)
        else:
            return self.no_response()

    def no_response(self, args=None):
        self.no_response_count += 1
        self.no_response_file_number += 1
        file_name = 'DSSD_1_3538_{}.wav'.format(self.no_response_file_number)
        log.debug('No response played : %s' % file_name)
        if self.no_response_count < 4:
            df = self.play_no_response(file_name)
            df.addCallback(self.record_keyword)
            return df
        else:
            msg = {'response': 'no response timed out'}
            return defer.fail(msg)
    
    def string_check(self, data):
        log.debug('data received for check string contains in or not : %s ' % data)
        a = data.split()
        # log.debug(a)
        for i in a:
            # log.debug('character to match : %s' % i)
            for j in self.protocol.call_detail_dict.keys():
                # log.debug('character search in : %s' % j)
                if i in j:
                    # log.debug('%s in %s' % (i, j))
                    self.protocol.speech_transcribe_keyword_data = j
                    return True
                # else:
                #    pass
        return False

    def start_keyword_match(self, args=None):
        log.debug('Start processing after keyword match')
        log.debug('Keyword matched with : %s' % self.protocol.speech_transcribe_keyword_data)
        self.set_channel_variables('speech_transcribe_data', self.protocol.speech_transcribe_keyword_data)
        self.keyword_heard = True
        # df = self.play_keyword_heard()
        # df.addCallback(self.record_keyword)
        # return df
        if self.protocol.speech_transcribe_keyword_data == 'demo':
            df = self.play_keyword_confirm_demo()
            df.addCallback(self.record_keyword)
            return df
        elif self.protocol.speech_transcribe_keyword_data in ['mb', 'message broadcast']:
            df = self.play_keyword_confirm_mb()
            df.addCallback(self.record_keyword)
            return df
        elif self.protocol.speech_transcribe_keyword_data == 'salem':
            df = self.play_keywork_confirm_salem()
            df.addCallback(self.record_keyword)
            return df
        else:
            df = self.set_channel_variables('speech_transcribe_data', self.protocol.speech_transcribe_keyword_data)
            df.addCallback(self.play_keyword_heard),
            df.addCallback(self.record_keyword)
            return df
        # df = self.set_channel_variables('speech_transcribe_data', self.protocol.speech_transcribe_keyword_data)
        # df.addCallback(self.play_keyword_heard),
        # df.addCallback(self.record_keyword)
        # return df

    def set_channel_variables(self, channel_variable_name, channel_variable_data):
        log.debug('setting channel variables :: %s = %s' % (channel_variable_name, channel_variable_data))
        return self.protocol.set(channel_variable_name, channel_variable_data)

    def after_keyword_speech_not_detected(self, args=None):
        log.debug('speech not detected in keyword confirmation.')
        if self.keyword_heard_speech_not_detected:
            return self.speech_transcribe_decision(data='continue')
        self.keyword_heard_speech_not_detected = True
        df = self.play_second_time_for_speech_input()
        df.addCallback(self.record_keyword)
        return df

    def after_keyword_heard(self, args=None):
        log.debug('processing on speech transcribe after keyword heard/matched.')
        log.debug('Received args : %s' % args)
        # speech_transcribe_detected.send(sender=self.after_keyword_heard,
        #                                 uuid=self.protocol.uuid, event=args,
        #                                 web_hook_url=self.protocol.web_hook_url, speech=args, send_text='',
        #                                 caller_id=self.protocol.inbound_call_info['Caller-Orig-Caller-ID-Number'])
        if self.protocol.processed_action_via_digit:
            log.debug('Need to continue. because, user has entered dtmf.')
            msg = {'response': 'entered dtmf'}
            return defer.succeed(msg)
        if args:
            if args.endswith('.'):
                args = args[:-1]
            args = args.lower()
            # if args in ['yes', 'yeah', 'ok']:
            #     msg = {'response': True}
            #     log.debug('response can be send : %s' % msg)
            #     return defer.succeed(msg)
            if self.protocol.processed_action_via_digit:
                log.debug('Need to continue. because, user has entered dtmf.')
                msg = {'response': 'entered dtmf'}
                return defer.succeed(msg)
            elif args in ['no']:
                msg = {'response': False}
                log.debug('string not matched. response can be send : %s' % msg)
                return defer.fail(msg)
            else:
                msg = {'response': True}
                log.debug('Processing for call bridge. response can be send : %s' % msg)
                return defer.succeed(msg)
        else:
            # msg = {'response': False}
            # log.debug('response can be send : %s' % msg)
            # return defer.fail(msg)
            # if self.keyword_heard_speech_not_detected:
            #     msg = {'response': True}
            #     log.debug('second time speech not detected.')
            #     log.debug('Processing for call bridge. response can be send : %s' % msg)
            #     return defer.succeed(msg)
            # return self.start_keyword_match(second_time=True)
            msg = {'response': True}
            log.debug('Processing for call bridge. response can be send : %s' % msg)
            return defer.succeed(msg)

    def after_pre_connecting_question(self, args=None):
        log.debug('processing on speech transcribe after pre connection question.')
        log.debug('Received args : %s' % args)
        # speech_transcribe_detected.send(sender=self.after_pre_connecting_question,
        #                                 uuid=self.protocol.uuid, event=args,
        #                                 web_hook_url=self.protocol.web_hook_url, speech=args, send_text=args,
        #                                 caller_id=self.protocol.inbound_call_info['Caller-Orig-Caller-ID-Number'])
        # if args:
        #     if args.endswith('.'):
        #         args = args[:-1]
        #     args = args.lower()
        #     if args in ['yes', 'no']:
        #         msg = {'response': True}
        #         log.debug('response can be send : %s' % msg)
        #         return defer.succeed(msg)
        #     else:
        #         msg = {'response': False}
        #         return defer.fail(msg)
        # else:
        #     msg = {'response': False}
        #     return defer.fail(msg)
        msg = {'response': True}
        log.debug('response can be send : %s' % msg)
        return defer.succeed(msg)

    def action_call_bridge(self, args=None):
        log.debug('Start call bridging.')
        try:
            # if self.protocol.speech_transcribe_keyword_data in self.protocol.call_detail_dict.keys():
            self.protocol.call_bridge_url = "{absolute_codec_string='PCMA,PCMU'}" + self.protocol.call_bridge_url
            bridge_url = self.protocol.call_bridge_url % self.protocol.call_detail_dict.get(self.protocol.speech_transcribe_keyword_data)
            log.debug('call will be bridge to : {}'.format(bridge_url))
            df = self.play_before_call_bridge()
            df.addCallback(self.action.start_command, cmd_name='bridge', cmd_args=bridge_url)
            return df
            # return self.action.start_command('bridge', bridge_url)
        except Exception as e:
            log.error('Error captured at call bridge : %s' % e)
            msg = {'response': 'error during call bridging'}
            return defer.fail(msg)

    def after_invalid_response_2(self, args=None):
        log.debug('processing on speech transcribe after keyword heard/matched.')
        log.debug('Received args : %s' % args)
        if args:
            if args.endswith('.'):
                args = args[:-1]
            args = args.lower()
            if args in ['yes']:
                self.protocol.speech_transcribe_keyword_data = 'mb'
                return self.start_keyword_match()
                # msg = {'response': True}
                # return defer.succeed(msg)
            else:
                msg = {'response': False}
                return defer.fail(msg)
        else:
            msg = {'response': False}
            return defer.fail(msg)

    def after_invalid_response(self, args=None, digit=None, data=None):
        log.debug('After invalid response, call processing further.')
        log.debug(self.protocol.processed_action_via_digit)
        if digit == '0' and self.protocol.processed_action_via_digit:
            self.protocol.speech_transcribe_keyword_data = 'mb'
            return self.start_keyword_match()
        # elif not self.protocol.processed_action_via_digit:
        #     df = self.start_google_speech_api_defer()
        #     df.addCallback(self.after_invalid_response_2)
        #     df.addErrback(self.def_responses.fail_response, message='invalid reponse 2 times')
        #     return df
        elif not self.protocol.processed_action_via_digit:
            df = self.after_invalid_response_2(data)
            df.addErrback(self.def_responses.fail_response, message='invalid reponse 2 times')
            return df
        else:
            log.error('Something wrong after two time invalid response.')
            msg = {'response': 'somethinge wrong'}
            return defer.fail(msg)
