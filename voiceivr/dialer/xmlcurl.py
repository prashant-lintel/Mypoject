#!/usr/bin/python 

import string 
import md5 
from random import choice

from twisted.internet import reactor, defer, error
from twisted.web import server , resource
from twisted.application import service, internet

import utils

config=utils.config

log=utils.get_logger('xmlcurl')


templates = {}
templates['unknown_result'] = '''<?xml version='1.0' encoding='UTF-8' standalone='no'?>
<document type='freeswitch/xml'>
<section name='result'>
<result status='not found' />
</section>
</document>
'''

templates['IVR_TEST'] = '''
    <include>
	<menu name="IVR_TEST"
        greet-long="test_msg.wav"
        greet-short="test_msb.wav"
        invalid-sound="silence_stream://1000"
        exit-sound="silence_stream://1000"
        timeout ="10000"
        inter-digit-timeout="2000"
        max-failures="1"
        digit-len="1">
            <entry action="menu-play-sound" digits="1" param="silence_stream://1000"/>
        </menu>
    </include>

'''


class XmlCurl(resource.Resource):
    def __init__(self):
        log.debug("Initializing XmlCurl")
        self.sectioncallbacks = {
            "directory": self.handleDirectory,
            "dialplan": self.handleDialplan,
            "configuration": self.handleConfiguration,
            "languages": self.handleLanguages
        }
        resource.Resource.__init__(self)

    def render_POST(self, request):
        request_args = self.get_post_vars(request)
        log.debug("Processed switch_request %s, %s", request, request_args)
        section = request_args.get('section')
        try:
            self.sectioncallbacks[section](request, request_args)
        except KeyError as e:
            log.error("Got switch_request that we are not interested in")
            self.sendUnkown(request)
        return server.NOT_DONE_YET

    def handleDialplan(self,req, request_args):
        # s = lambda data:self.sendDialplan(data['ROWS'], request_args, req)
        log.debug("Returning not found for dialplan section")
        request.write(templates["unknown_result"])
        request.finish()

    def handleDirectory(self, request, request_args):
        log.debug("Returning not found for directory section")
        request.write(templates["unknown_result"])
        request.finish()

    def handleConfiguration(self, request, request_args):
        log.debug('Returning not found for configuration section')
        request.write(templates["unknown_result"])
        request.finish()

    def handleLanguages(self, request, request_args):
        log.debug("Returning not found for language section ")
        request.write(templates["unknown_result"])
        request.finish()

    def get_post_vars(self, req):
        vars = {}
        for k, v in req.args.items():
            vars[k] = v[0]
        return vars    

    def createCallobj(self,username,sr,req):
        coreUUID = sr['Core-UUID']
        callobj = CallObj(username,coreUUID)
        req.calls[coreUUID]=callobj

    def authError(self, error, req):
        if req.timeout.active():
            req.timeout.cancel()
        self.sendError(error, req)
        
    def sendTimeout(self, df, req):
        if df.called:
            log.debug("Request already finished")
            return
        else:
            self.sendError(error.TimeoutError(), req)

    def sendDialplan(self,data, sr, req):
        log.debug("Pricessing sendDialplan with data :%s",data)
        result = None #TODO: Give result received from webservice
        self.sendReply(result, req)
            
    def sendReply(self, result, req):
        """Send a success reply to FreeSWITCH
        result -- (str) xml string representing result 
        req -- twisted http request object
        """
        if req.finished:
            log.debug("Request already finished")
            return
        req.setResponseCode(200)
        req.setHeader("Content-Type", "text/plain")
        log.info("result xml :  \n %s ",result)
        req.write(result)
        req.finish()
        
    def sendError(self, error, req):
        """Send error reply to FreeSWITCH
        error -- (str) xml string representing result 
        req -- twisted http request object 
        """
        if req.finished:
            log.debug("Request already finished (from sendError method)")
            return
        log.exception("Error occured while performing , error info :%s",error)
        log.debug("Sending reply as Internal server Error")
        req.setResponseCode(500, "Internal Server Error")
        req.setHeader("Content-Type", "text/plain")
        req.finish()
        
    def sendUnkown(self, req):
        """Send unknown reply to FreeSWITCH 
        req -- twisted http request object """
        log.debug("Sending result unkown")
        result = templates['unknown_result']
        self.sendReply(result, req)
        

class XMLCurl(server.Site):
    def __init__(self, r, dialer):
        self.calls = dialer.calls
        self.requestFactory.calls = self.calls
        server.Site.__init__(self, r)


def getService(dialer):
    #start auth service
    r = XmlCurl()
    r.putChild('', r)
    f = XMLCurl(r, dialer)
    s = internet.TCPServer(config.getint("network", "xmlcurl_service_port"), f)
    return s

