import time
import collections
from twisted import application
from twisted.internet import reactor
from twisted.internet.task import LoopingCall, coiterate
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet.defer import inlineCallbacks, returnValue
from pyswitch import inbound
from dialer import utils
from dialer import call
# from .signals import (
#     channel_answer, channel_hangup, channel_bridge,
#     channel_ringing, channel_create,
#     channel_originate
# )


config = utils.config
log = utils.get_logger("inbound_socket")
MIN_STALECALL_CHECK_PERIOD = 120


class Inbound(inbound.InboundProtocol):
    def __init__(self, dialer):
        self.dialer = dialer
        self.calls = dialer.calls

    def authSuccess(self, msg):
        log.info("Successfully logged into the freeswitch")
        log.debug("Information from FS on connection, %s", msg)
        self.dialer.iprotocol = self
        self.registerEventCallbacks()

    def registerEventCallbacks(self):
        self.registerEvent('CHANNEL_ANSWER', True, self.channelAnswer)
        self.registerEvent('CHANNEL_CREATE', True, self.channelCreate)
        self.registerEvent('CHANNEL_HANGUP', True, self.channelHangup)
        self.registerEvent('CHANNEL_HANGUP_COMPLETE', True,
                           self.channelHangupComplete)
        self.registerEvent('CHANNEL_PROGRESS', True, self.channelProgress)
        self.registerEvent('CHANNEL_PROGRESS_MEDIA', True, self.channelProgressMedia)
        self.registerEvent('CHANNEL_ORIGINATE', True, self.channelOriginate)
        # self.registerEvent('CHANNEL_STATE', True, self.channelStatechange)
        self.registerEvent("BACKGROUND_JOB", True,
                           self.onBackgroundJobFinalEvent)
        self.startStaleCallCheck()

    def isItStrange(self, uuid):
        if uuid not in self.dialer.calls:
            log.warning("Strange EVENT  CHANNEL_CREATE")
            return True
        return False

    def channelOriginate(self, event):
        log.debug("  Event CHANNEL_ORIGINATE  ")
        uuid = event['Unique-id']
        if self.isItStrange(uuid):
            return
        # channel_originate.send(self.channelOriginate, uuid=uuid, event=event)

    def channelCreate(self, event):
        log.debug("Event CHANNEL_CREATE  ")
        uuid = event['Unique-id']
        if self.isItStrange(uuid):
            return
        # channel_create.send(self.channelCreate, uuid=uuid, event=event)

    def channelAnswer(self, event):
        uuid = event['Unique-id']
        if self.isItStrange(uuid):
            return
        log.info("Channel Answer %s", uuid)
        # channel_answer.send(sender=self.channelAnswer, uuid=uuid, event=event)

    def channelHangup(self, event):
        uuid = event['Unique-id']
        if self.isItStrange(uuid):
            return
        log.info("Firing signal CHANNEL_HANGUP")
        # channel_hangup.send(sender=self.channelHangupComplete,
        #                     uuid=uuid, event=event)

    def channelHangupComplete(self, event):
        uuid = event['Unique-id']
        if self.isItStrange(uuid):
            return
        log.info("Event Channel hangup complete on  %s", uuid)
        callobj = self.calls.pop(uuid)
        # callobj.hangup = True
        log.info("Popped call object %s", callobj)

    def channelProgress(self, event):
        uuid = event['Unique-id']
        if self.isItStrange(uuid):
            return
        log.info("### Channel progress aka channel ringing on %s ##", uuid)
        # channel_ringing.send(sender=self.channelProgress, uuid=uuid, event=event)

    def channelProgressMedia(self, event):
        uuid = event['Unique-id']
        if self.isItStrange(uuid):
            return
        log.info("### Channel progress aka channel ringing on %s ##", uuid)
        # channel_ringing.send(uuid, event)

    def onBackgroundJobFinalEvent(self, event):
        pass

    def startStaleCallCheck(self):
        self.stale_call_lc = LoopingCall(self.checkStaleCalls)
        self.stale_call_lc.start(60)

    @inlineCallbacks
    def checkStaleCalls(self):
        log.debug("Checking Stale Calls ....")
        #TODO: Optimize later with coiterator if required
        max_duration = config.getfloat('dialer', 'max_call_duration')
        for u, c in self.calls.items():
            originate_time = yield c.originate_time
            duration = utils.getUTC() - float(originate_time)
            print 'Duraion, max_duration: type:', duration, max_duration, type(duration), type(max_duration)
            if duration >= max_duration:
                log.warning("Stale call exceeding max duration: %s uuid: %s", u, duration)
                log.info("Stale call check hangup: uuid: %s: %s", u, c)
                self.hangup(uuid=u)

    @inlineCallbacks
    def getDialString(self, ph, uuid, callobj):
        d = config.get('fs','dial_string')
        caller_id = yield callobj.caller_id
        caller_id = caller_id or config.get('fs', 'default_caller_id')
        log.debug("Caller ID which going to be used: %s", caller_id)
        prefix = ('[origination_uuid=%s,return_ring_ready=true,'
                  'origination_caller_id_number=%s,'
                  'origination_caller_id_name=%s]') % (
            uuid, caller_id, caller_id)
        returnValue(str(prefix + d % ph))

    @inlineCallbacks
    def dialNumber(self, callobj, ph):
        uuid = callobj.uuid
        dial_string = yield self.getDialString(ph, uuid, callobj)
        log.info("Dial String: %s", dial_string)
        outbound_socket = config.get('fs', 'outbound_socket')
        df = self.apiOriginate(dial_string, 'socket', str(outbound_socket))
        df.addCallback(self.originateSuccess, ph)
        df.addErrback(self.originateFailed, ph)
        callobj.originate_time = utils.getUTC()
        callobj.destination_number = ph

    def originateSuccess(self, msg, ph):
        log.debug("Successfully originated a call %s", ph)

    def originateFailed(self, err, ph):
        log.exception("Failed to originate the call %s", ph)

    def send_api(self, api):
        log.debug('Request FS API: %s' % api)
        # return self..sendAPI(api)


class InboundFactory(ReconnectingClientFactory, inbound.InboundFactory):
    protocol = Inbound

    def __init__(self, passwd, master):
        """

        @param passwd: event-socket password
        @param master: the global object which mantains all records globally
        """
        self.master = master
        inbound.InboundFactory.__init__(self, passwd)

    def buildProtocol(self, addr):
        log.debug("Creating inbound protocol")
        p = self.protocol(self.master)
        p.factory = self
        self.master.inbound_socket = p
        global P
        P = p
        self.resetDelay()
        return p

    def clientConnectionLost(self, connector, reason):
        log.error("Lost connection to FREESWITCH. Reason: %s", reason)
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        log.error("Connection failed with Freeswitch. Reason: %s", reason)
        ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)


def getFsInboudSocketDetails():
    esp = config.get('fs', 'inbound_socket_passwd')
    port = config.getint('fs', 'inbound_socket_port')
    ip = config.get('fs', 'ip')
    return str(esp), port, ip


def getService(master):
    """

    @param master: A globally shared object
    @return: service
    """
    esp, port, ip = getFsInboudSocketDetails()
    f = InboundFactory(esp, master)
    s = application.internet.TCPClient(ip, port, f)
    return s


if __name__ == '__main__':
    calls = {}
    esp, port, ip = getFsInboudSocketDetails()
    f = InboundFactory(esp, calls)
    reactor.connectTCP(port, ip, f)
    reactor.run()
