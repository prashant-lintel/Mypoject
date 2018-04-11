#!/usr/bin/python

"""This module deals with the switching nodes of dialer"""
import sys
import time
# import utils
import traceback
import urllib
import collections
from twisted.protocols import basic
from twisted.internet import reactor, defer, protocol
import json
import logging
import utils

log = utils.get_logger("JSONNode")
# config = utils.get_node_config()
config = utils.config
# log.setLevel(config.get("general", "jsonnode_loglevel"))


if sys.hexversion < 0x020500f0:
    from email.Message import Message
    from email.FeedParser import FeedParser
else:
    from email.message import Message
    from email.feedparser import FeedParser


class CommandError(Exception):
    pass


class NodeMessage(collections.MutableMapping):
    def __init__(self, store=None):
        if not store:
            self.store = {}
        else:
            self.store = store

    def __getitem__(self, item):
        return self.store[item]

    def __setitem__(self, key, value):
        self.store[key] = value

    def __delitem__(self, key):
        """
        Dont rise KeyError traditionally NodeMessage class never rose
        KeyError while dealing with non existant key.
        :param key: dictionary key
        """
        if key in self.store:
            del self.store[key]

    def __iter__(self):
        return self.store.__iter__()

    def __len__(self):
        return len(self.store)

    def as_string(self):
        return json.dumps(self.store)


# useful when serialized by json
NodeMessage.register(dict)


class EventCallback:
    def __init__(self, eventname, func, *args, **kwargs):
        self.func = func
        self.eventname = eventname
        self.args = args
        self.kwargs = kwargs


def command(command):
    """Used as a decorator to add methods which implment node commands to commandCallbacks"""

    def wrap(f):
        NodeProtocol.commandCallbacks[command] = f
        return f

    return wrap


class NodeProtocol(basic.LineReceiver):
    delimiter = "\n\n"
    commandCallbacks = {}
    pendingJobs = {}  # will be reset on connectionMade
    authed = False
    connected = False
    MAX_LENGTH = 2000000

    def connectionMade(self):
        self.connected = True
        log.info("Connected to node")
        """Initialize Nodeprotocol arguments are ignored """
        # basic.LineOnlyReceiver.__init__(self)
        self.contentCallbacks = {"auth/request": self.authRequest,
                                 "auth/reply": self.authReply,
                                 "command/request": self.commandRequest,
                                 "command/reply": self.commandReply,
                                 "heartbeat/request": self.heartBeatRequest,
                                 "heartbeat/reply": self.heartBeatReply,
                                 "text/event-plain": self.dispatchEvent,
                                 "text/disconnect-notice": self.disconnectNotice,
                                 "transport/request": self.transportRequest,
                                 "transport/reply": self.transportReply
                                 }
        self.pendingJobs = {}
        self.eventCallbacks = []
        self.subscribedEvents = []
        self.authed = False

    def connectionLost(self, reason):
        self.connected = False
        self.authed = False
        log.error("Disconnected from node reason -%s" % reason)

    def registerEvent(self, event, function, *args, **kwargs):
        """Register a callback for the event
        event -- (str) Event name as sent by FreeSWITCH
        function -- callback function accepts a event dictionary as first argument
        args -- argumnet to be passed to callback function
        kwargs -- keyword arguments to be passed to callback function

        returns instance of  EventCallback , keep a reference of this around if you want to deregister it later
        """

        """"if self.needToSubscribe(event):
            self.subscribeEvents(event)"""
        ecb = EventCallback(event, function, *args, **kwargs)
        self.eventCallbacks.append(ecb)
        return ecb

    def deregisterEvent(self, ecb):
        """Deregister a callback for the given event

        ecb -- (EventCallback) instance of EventCallback object
        """
        try:
            self.eventCallbacks.remove(ecb)
        except ValueError:
            log.error("%s already deregistered " % ecb)

    def lineReceived(self, line):
        log.debug("Line In: %s" % line)
        self.message = NodeMessage(json.loads(line))
        try:
            self.inspectMessage()
        except:
            log.error('Caught exception :', exc_info=True)

    def inspectMessage(self):
        if not "Content-Type" in self.message:
            return
        ct = self.message['Content-Type']
        try:
            cb = self.contentCallbacks[ct]
        except KeyError:
            log.error("Got unimplemented Content-Type callback: %s" % ct, exc_info=True)
            return
        cb()

    def transportRequest(self):
        """
        Handle underlying socket transport change request
        """
        if self.message['transport'] == "TLS":
            self.startTLS()

    def transportReply(self):
        """
        Handle transport reply
        """
        pass

    def startTLS(self):
        """
        Override this method for implementing TLS negotiation with key and certificate
        Decide here if we are ready for TLS and create TLS Context if so.
        """
        pass

    def tlsReady(self, context):
        """
        Send a indication that we are ready for TLS and start negotiation

        """
        self.transport.startTLS(context, self.factory)

    def authRequest(self):
        """Over-ride this method and reply with auth information (client side)"""
        pass

    def authReply(self):
        """Override this method to do credential verification

        server side - use for check credentials
        client side - use for checking server reply"""

    def commandRequest(self):
        """Process command request """
        if not self.authed:
            return self.sendDisconnect("Need to authenticate first ")
        command = self.message['command']
        cmd_cb = self.commandCallbacks[command]
        try:
            cmd_cb(self, self.message)
        except:
            log.error("Error in executing command ", exc_info=True)
            self.sendFailure(self.message['msg-uuid'], "Internal server error")

    def sendCommand(self, msg):
        """Send a command request to other side of the connection"""
        if not self.authed:
            if __debug__:
                log.debug("Not authenticated yet dropping sendCommand")
            return
        df = defer.Deferred()
        uuid = utils.getUUID()
        self.pendingJobs[uuid] = df
        del msg['Content-Type']
        msg['Content-Type'] = 'command/request'
        del msg['msg-uuid']
        msg['msg-uuid'] = uuid
        self.sendMessage(msg)
        return df

    def sendCommandReply(self, msg):
        """Send a reply to previoiusly received command """
        msg['Content-Type'] = "command/reply"
        self.sendMessage(msg)

    def sendAuthReply(self, msg):
        """Send authentication reply to client """
        msg['Content-Type'] = 'auth/reply'
        self.sendMessage(msg)

    def heartBeatRequest(self):
        """Handle heart beat request """
        if __debug__:
            log.debug("Received Heart beat %s" % self.message)
        m = NodeMessage()
        m['Content-Type'] = 'heartbeat/reply'
        m['Reply-Text'] = '+OK Alive'
        m['timestamp'] = time.time()
        m['msg-uuid'] = self.message['msg-uuid']
        self.sendMessage(m)

    def heartBeatReply(self):
        """Handle heart beat reply """
        pass

    def sendMessage(self, msg):
        """Write NodeMessage object on wire"""
        if not 'msg-uuid' in msg:
            msg['msg-uuid'] = utils.getUUID()
        m = msg.as_string()
        if __debug__:
            log.debug("Sending msg out :%r" % m)
        if self.connected:
            # old NodeMessage class returned string with delimiter included which is not good
            # self.transport.write(m)
            self.sendLine(m)

    def sendSuccess(self, msg_uuid, text=None):
        """Send a success command reply
        msg_uuid -- (str) uuid of the request message received
        msg - (str) success text that needs to included in reply message"""
        m = NodeMessage()
        if text:
            m['Reply-Text'] = ' '.join(['+OK', text])
        else:
            m['Reply-Text'] = '+OK'
        m['msg-uuid'] = msg_uuid
        self.sendCommandReply(m)

    def sendFailure(self, msg_uuid, text=None):
        """Send failure respone to a command
        msg_uuid -- (str) uuid of the request message received
        text -- (str) error text that needs to included in reply message"""
        m = NodeMessage()
        if text:
            m['Reply-Text'] = ' '.join(['-ERR', text])
        else:
            m['Reply-Text'] = '-ERR'
        m['msg-uuid'] = msg_uuid
        self.sendCommandReply(m)

    def commandReply(self):
        """
        Handle CommandReply
        """
        try:
            df = self.pendingJobs.pop(self.message['msg-uuid'])
        except KeyError:
            log.error("Command Reply received with stray uuid ")
            return
        if df.called:
            log.error("Command reply deferred already called %s" % self.message['msg-uuid'])
            return
        if self.message['Reply-Text'].startswith("+OK"):
            df.callback(self.message)
        else:
            e = CommandError(self.message['Reply-Text'])
            df.errback(e)

    def dispatchEvent(self):
        """Dispatch event messages to resigsted callbacks """
        eventname = self.message['Event-Name']
        for ecb in self.eventCallbacks:
            if ecb.eventname != eventname:
                continue
            try:
                ecb.func(self.message, *ecb.args, **ecb.kwargs)
            except:
                log.error("Error in event handler %s on event %s" % (ecb.func, eventname), exc_info=True)

    def disconnectNotice(self):
        """Override this to get disconnect notice"""
        pass

    def sendEvent(self, msg):
        """Send event to other side of the wire """
        msg['Content-Type'] = 'text/event-plain'
        self.sendMessage(msg)

    def sendDisconnect(self, msg):
        """Send disconnect message and close connection"""
        m = NodeMessage()
        m['message'] = msg
        m['Content-Type'] = 'text/disconnect-notice'
        self.sendMessage(m)
        self.transport.loseConnection()


class NodeServerProtocol(NodeProtocol):
    def connectionMade(self):
        # add authReply content type
        # self.contentCallbacks['command/request'] = self.commandRequest
        NodeProtocol.connectionMade(self)
        log.info("New node connection from %s" % self.transport.getPeer())
        self.log = utils.get_logger("Node:%s" % self.transport.getPeer())
        self.authed = True
        # self.askAuthentication()

    def askAuthentication(self):
        self.log.debug("Asking authentication")
        msg = NodeMessage()
        msg['Content-Type'] = "auth/request"
        self.sendLine(msg.as_string())

    def authReply(self):
        """Override this in your own protocol """
        pass

    def commandReply(self):
        if self.authed or self.message['command'] == 'auth':
            return NodeProtocol.commandReply(self)
        else:
            msg = "Need to authenticate first "
            log.error(msg)
            return self.sendDisconnect(msg)


class NodeClientProtocol(NodeProtocol):
    def connectionMade(self):
        NodeProtocol.connectionMade(self)
        self.authed = True

    def authRequest(self):
        """Override this method and reply with auth info"""
        cmd = NodeMessage()
        cmd['command'] = 'auth'
        cmd['name'] = 'switch'
        cmd['password'] = None

    def sendAuthReply(self, msg):
        self.authdf = defer.Deferred()
        NodeProtocol.sendAuthReply(self, msg)
        return self.authdf

    def authReply(self):
        print "called"
        if self.message['Reply-Text'].startswith("+OK"):
            self.authdf.callback(True)
        else:
            self.authdf.errback(self.message)
        del self.authdf


class NodeProtocolUDP(NodeProtocol):
    """Node UDP protocol is intended switching nodes to communicate among one another
    inteded light weight, currently authentication is not required
    """

    def __init__(self, addr):
        self.addr = addr
        # NodeProtocol.__init__(self)

    def connectionMade(self):
        log.info('Got new UDP connection from %s', self.addr)
        NodeProtocol.connectionMade(self)
        self.authed = True  # Set this to True as there is no authentication implemented currently

    def askAuthentication(self):
        pass

    def sendMessage(self, msg):
        """Write NodeMessage object on wire"""
        if not 'msg-uuid' in msg:
            msg['msg-uuid'] = utils.getUUID()
        m = msg.as_string()
        if __debug__:
            log.debug("Sending msg out :%r" % m)
        if self.connected:
            # self.transport.write(m, self.addr)
            self.transport.write(m + self.delimiter, self.addr)


class NodeProtocolUDPBase(protocol.DatagramProtocol):
    def __init__(self, proto):
        self._clients = {}
        self.protocol = proto

    def datagramReceived(self, data, addr):
        client = self.getProtocol(addr)
        client.dataReceived(data)

    def getProtocol(self, addr):
        try:
            client = self._clients[addr]
        except KeyError:
            client = self.protocol(addr)
            client.transport = self.transport
            self._clients[addr] = client
            client.connectionMade()
        return client
