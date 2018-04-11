import json
from twisted.web.http_headers import Headers
from twisted.web.iweb import IBodyProducer
from zope.interface import implements
from twisted.internet import reactor, defer
from twisted.web.client import Agent
# here,we use oauth2client==4.1.2
from oauth2client.service_account import ServiceAccountCredentials
import utils

config = utils.config
log = utils.get_logger('speech_api')

# SERVICE_ADDRESS = "https://speech.googleapis.com/v1/speech:longrunningrecognize"
SERVICE_ADDRESS = "https://speech.googleapis.com/v1/speech:recognize"
"""The default address of the service."""

# sample rate of audio
SAMPLE_RATE = 8000

ENCODING = "LINEAR16"

LANGUAGE_CODE = "en-US"

speech_file_path = '/home/deepen/Downloads/second_time_ask1.wav'

SERVICE_ACCOUNT = {
  "type": "service_account",
  "project_id": "hypnotic-epoch-114119",
  "private_key_id": "16539c2b45c41114d96fef71530c97fbd40ad3ac",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCkNa2xq4CwREEJ\n8WFHMLSInU2cD+PIIteV19civKljv0mskhVTtAd16kP51+v6XW3LggZb/bs9BKM6\npOfpUwsrivdBDvf4w3/aI4GCgaHrLLKuX1p4BWZLCxsQ6jdRfPE4pcfHmrOFE9nr\nlpmKNfz3mDpmyhraKDOsoMLmsYjvkeA+AIPIM79K/SPKRWbglWtlWEgxe3FZ9ub2\nzfuioEAIZyyLzJe+7cYGjGeJMEvzs1hsqKI92LQU31uer0u1BmAHf0mRLS9SUMRz\nUwrJZUBcQJZFd5j7Sxtu071AqAn9JiPTy5sO2oRbm9JbZ3/47IkIKxjYBP2b37kf\nZOd9CwXLAgMBAAECggEADIkYgGayRUKAoIyvu2qJbaBsi0xfPCkEwiifAMTcPYQd\n0LG6NRCaPTMsC0ejeRJmzlFXwPAGuiq/dzudhJ9VS/ao12uYHIJ4ISPywA67WKOp\n5EvdMSpgW7w2Tb1DidH67DMjpCY4LCGO0kBF6loivJf/ZVdqY1sMTtJa7peA96DQ\n1Jn/zKepaVB4psv8ZPbIdERO7NbQSjW7lZQv2uSjLVRsTXjyA+Ntje9oBg0Akhn7\nPJm93D+al1KFtk/slAAuCInKXGoEFsr/zt94QwCN0xqL/gieSL10zhgp6u0Yp2Di\njAUKg1/+qH24c1KWXbiVgkNV/EPKIX7c/IutyUXyMQKBgQDc1t3HfsgMQ6dUDbWj\nKpLTspDxv//SUiteeOPKD/2mbgcOOSiel193+ZVuaT8WybJYY79Yg4yh5efqMDUh\n7HGdJSjNDU0xXnkXWhrwZU9ZFKE53ld0MFI9UBnrfqRfELwcjVQ/glb2JeBjmMoE\nlnIirF6NhxWCZv/Spom0xo6FswKBgQC+Wqi6NODSjNeHAuMB1UP3LX6q3XamtGNP\n1Nz4QlNItL+ETv6r5bq/k6Tza+1jq/IXskhjXTJKN7Xx0uPVW6dvsoDpMDGh6KHD\nnppxjy32PR0hUuHn1PajtSpJ8y/zWtxyYKKEaW/ah5VqtzPVUxQm3YVn+oWkloGE\n+UHTpIojiQKBgQCgK+NNJyIW6xa4uvzLrDwz+OZxwKzeMaSs74dfbbut802Avmo8\npFOk48vC+ei9MWr9+tK0cy0T23kafP58bU52CJaQKp6bOQcgrcSuKPylAnZxT1ck\nuUtclvVFvWOgY7XcC5FYQsOp4gzej9mt/CQqC9TEV359RxEzCoEEMaL7SwKBgQCc\nMafhoyIXopn3ntbG2kg6uooFilOh1sLm7rOiwkm0jxvXZTpzsr3aFTx0wUq5To4I\nA7KCVia935jcJT/uApcRgFdnALS5NjoGWk5AgEwmkV8lyOy1XnpDOpTIuVPPS+83\nqzOvkxTFLBvexRUzJkiS25JsD5U5yIXepujs0UbIgQKBgFkO3nhE5CW13EDfUwxD\npI0b6Js3poriMAolsp5Qi0sAODNys3EoxwH2vpFWJUKk9qlAjEeY7ME8DYnI/VjR\nQDtOpkmriAlBVUYErLjimj99i7WjTPT/GD9zfa90qAdbTU/Z4EwRXtSaJMDxU0b3\neTBQrMWB138hfzcS9iapFcd2\n-----END PRIVATE KEY-----\n",
  "client_email": "hypnotic-epoch-114119@appspot.gserviceaccount.com",
  "client_id": "118009337345476608531",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://accounts.google.com/o/oauth2/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/hypnotic-epoch-114119%40appspot.gserviceaccount.com"
}

json_dict_fetch = None


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


class RestSpeechAPI:
    """
    It is provides object for speech transcribed using twisted.
    """

    def __init__(self):
        self.payload = None
        # self.start_process()
        self.json_dict = None
        self.initial_process()

    def initial_process(self):
        """
        Initialize access token.
        :return: None
        """
        self.json_dict = ServiceAccountCredentials.from_json_keyfile_dict(keyfile_dict=SERVICE_ACCOUNT,
                                                                           scopes='https://www.googleapis.com/auth/cloud-platform')
        self.json_dict.get_access_token()

    def start_process(self, data=None):
        """
        It call google speech rest api using audio chunk data.
        :param data: audio data.
        :return: defer callback.
        """
        # df = Deferred()
        # df.addCallback(self.convert_audio)
        # global json_dict_fetch
        # json_dict_fetch = ServiceAccountCredentials.from_json_keyfile_dict(keyfile_dict=SERVICE_ACCOUNT,
        #                                                                    scopes='https://www.googleapis.com/auth/cloud-platform')
        # json_dict_fetch.get_access_token()
        df = self.convert_audio(data=data)
        df.addCallback(self.call_api)
        df.addErrback(self.errCallback)
        # df.callback('Speech api')
        return df

    def errCallback(self, args=None):
        print('error callback : %s' % args)
        return args

    def call_api(self, args=None):
        agent = Agent(reactor)
        global json_dict_fetch
        d = agent.request(
            'POST',
            # 'GET',
            SERVICE_ADDRESS,
            Headers(
                {
                    'Content-Type': ['application/json', ],
                    'Authorization': ['Bearer %s' % str(self.json_dict.access_token), ],
                }
            ),
            StringProducer(self.payload)
        )
        return d

    def convert_audio(self, args=None, data=None):
        # encoding audio file with Base64 (~200KB, 15 secs)
        try:
            curl_config = {
                "config": {
                    "encoding": ENCODING,
                    "sampleRateHertz": SAMPLE_RATE,
                    "languageCode": LANGUAGE_CODE,
                    "enableWordTimeOffsets": False,
                },
                "audio": {
                    "content": data.decode('UTF-8'),
                },
            }

            self.payload = json.dumps(curl_config)
            return defer.succeed('payload complete')
        except Exception as e:
            print('Error during payload creation: %s' % e)
            return defer.fail({'msg': 'fail during payload creation'})
