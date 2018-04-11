import ast
from twisted.internet import reactor, protocol
from twisted.internet import defer
from txredis import RedisClient
from dialer import utils
# from dialer.signals import channel_originate

log = utils.get_logger("call")
conf = utils.config

_redis = None

USE_REDIS = True


def connectRedis(host='127.0.0.1', port=6379):
    log.debug("Connecting to redis..... ")
    redis = protocol.ClientCreator(reactor, RedisClient)
    df = redis.connectTCP(host, port)
    df.addCallback(onRedisConnect)
    df.addErrback(onRedisConnectFailure, host, port)
    return df


def onRedisConnect(redis):
    global _redis
    log.info("Successfully connected to redis")
    _redis = redis
    Call.redis = redis
    initStats(redis)


def onRedisConnectFailure(err, host, port):
    log.exception("Failed to connect redis %s:%s", host, port)

connectRedis(
    conf.get('network', 'redis_host'), conf.getint('network', 'redis_port')
)


class StatsDescriptor(object):
    # redis = None  #Redis Connection Object
    key = 'stats'

    def __init__(self, name):
        self.name = name
        _redis.hset(self.key, self.name, 0)
        # self.value = 0

    def __get__(self, instance, owner):
        return self

    @property
    def value(self):
        df = _redis.hget(self.key, self.name)

        def postProcess(result):
            return result.get(self.name)
        return df.addCallback(postProcess)

    def __set__(self, instance, value):
        print 'Setting %s' % self.name
        if isinstance(value, (int, float, str)):
            _redis.hset(self.key, self.name, value)

    def __add__(self, other):
        self.incrByRedis(other)
        return self

    def __iadd__(self, other):
        self.incrByRedis(other)
        return self

    def __sub__(self, other):
        self.incrByRedis(-other)
        return self

    def __isub__(self, other):
        self.incrByRedis(-other)
        return self

    def incrByRedis(self, value):
        _redis.hincrby(self.key, self.name, value)


class LiveCallsDescriptor(object):
    key = 'live_calls'

    def __get__(self, instance, owner):
        return self

    @property
    def value(self):
        df = _redis.hget(self.key, self.name)

        def postProcess(result):
            return result.get(self.name)
        return df.addCallback(postProcess)

    def count(self):
        df = _redis.scard(self.key)
        return df

    def doEmpty(self):
        _redis.delete(self.key)

    def add(self, uuid):
        _redis.sadd(self.key, uuid)

    def remove(self, uuid):
        _redis.srem(self.key, uuid)


class Stats(object):
    key = 'stats'

    def __new__(cls, *args, **kwargs):
        log.info("Creating stats object ... ")
        obj = object.__new__(cls)
        return obj

    def __init__(self):
        log.info("Initializing stats object ")

    def getStats(self, stats=None):
        """
        Returns requested stats
        @type stats: None or tuple or list. If None, returns all stats

        response would look like
         {"total_calls": 10, "live_calls": 1,
         "total_bridged": 3, "live_bridged": 2}
        """
        return self.items()

    def __str__(self):
        return "<stats>"

    def getAttribs(self, attribs):
        pass

    def items(self):
        df = _redis.hgetall(self.key)
        df.addCallback(toDict)
        return df

    def reset(self):
        """
        Reset All Stats
        """
        self.total_calls = 0
        self.live_calls.doEmpty()
        self.total_bridged = 0
        self.live_bridged = 0


def initStats(redis):
    Stats.total_calls = StatsDescriptor("total_calls")
    Stats.live_calls = LiveCallsDescriptor()
    Stats.total_bridged = StatsDescriptor("total_bridged")
    Stats.live_bridged = StatsDescriptor("live_bridged")
    Stats.redis = redis


def toDict(result):
    log.debug("Converting result from redis dict to python objects: %s", result)
    if isinstance(result, dict):
        for i, v in result.items():
            try:
                result[i] = ast.literal_eval(v)
            except SyntaxError as e:
                result[i] = v
            except:
                result[i] = v
    return result


class Dialer(object):
    """The master shared object"""

    # The calls dictionary {"uuid": callobj}
    calls = {}
    stats = Stats()

    # FreeSwitch inbound protocol
    iprotocol = None

    inbound_calls_dialer_reference = {}

    def __new__(cls, *args, **kwargs):
        obj = super(Dialer, cls).__new__(cls)
        return obj

    def __init__(self):
        pass

    def dialNumber(self, callobj, ph):
        return self.iprotocol.dialNumber(callobj, ph)


class Call(object):
    """The Call Object Which Holds Call Information"""

    redis = _redis

    def __new__(cls, number, *args, **kwargs):
        log.debug("Creating call object ... ")
        obj = object.__new__(cls)
        uuid = utils.getUUID()
        # cls.__init__(obj, number, uuid)
        if USE_REDIS:
            key = "call:%s" % uuid
            cls.redis.hmset(key, {"uuid": uuid, "number": number})
            obj.__dict__['uuid'] = uuid
            dialer.calls[uuid] = obj
        return obj

    def __init__(self, number):
        log.debug("Initializing call object %s", number)
        self.__dict__['redis_key'] = "call:%s" % self.uuid
        self.__dict__['number'] = number

    def __str__(self):
        return "<call: %s>" % self.uuid

    def getKey(self):
        return "call:%s" % self.uuid

    def getAttribs(self, attribs):
        pass

    def items(self):
        df = self.redis.hgetall(self.getKey())
        df.addCallback(toDict)
        return df

    def __del__(self):
        self.delete()

    def delete(self):
        key = self.getKey()
        print "Deleting key %s" % key
        log.info("Removing key %s from redis", key)
        return self.redis.delete(self.getKey())

    def __getattr__(self, item):
        def getValue(result, item):
            if not isinstance(result, dict):
                return result
            return result[item]

        try:
            return self.__dict__[item]
        except KeyError as e:
            key_name = self.getKey()
            df = self.redis.hget(key_name, item)
            df.addCallback(getValue, item)
            return df

    def __setattr__(self, key, value):
        key_name = self.getKey()
        df = self.redis.hset(key_name, key, value)
        return df


def createCallObj(ph, action, action_args, **kwargs):
    try:
        call = Call(ph)
    except AttributeError as e:
        log.exception("Unable to create call object. Check if redis running")
    else:
        call.action = action
        call.action_args = action_args
        return call

dialer = Dialer()

