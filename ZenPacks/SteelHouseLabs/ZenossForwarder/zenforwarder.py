import time
import socket
import os
import logging

from twisted.internet import reactor, defer
from twisted.python import failure

import json
import urllib
import urllib2

import pika

import Globals
import zope.interface
import zope.component

from Products.ZenUtils.GlobalConfig import getGlobalConfiguration

from Products.ZenCollector.daemon import CollectorDaemon
from Products.ZenCollector.interfaces import ICollector, ICollectorPreferences,\
                                             IEventService, \
                                             IScheduledTask, IStatisticsService
from Products.ZenCollector.tasks import SimpleTaskFactory,\
                                        SimpleTaskSplitter,\
                                        BaseTask, TaskStates
from Products.ZenUtils.observable import ObservableMixin

from Products.ZenUtils.Utils import zenPath

from Products.ZenEvents.EventServer import Stats
from Products.ZenUtils.Utils import unused
from Products.ZenCollector.services.config import DeviceProxy

from ZenPacks.SteelHouseLabs.ZenossForwarder.services.ZEFService import ZEFService
unused(Globals, DeviceProxy)

COLLECTOR_NAME = 'zenossforwarder'
log = logging.getLogger("zen.%s" % COLLECTOR_NAME)

global_conf = getGlobalConfiguration()

destinationHost = global_conf.get('zenforwarderDestinationUrl', 'http://10.0.0.2:8080')
zenuser = global_conf.get('zenuser', 'admin')
zenpass = global_conf.get('zenpass', 'zenoss')

exchange = 'events'
queue = 'eventForwarder'
passwd = global_conf.get('amqppassword', 'zenoss')
user = global_conf.get('amqpuser', 'zenoss')
vhost = global_conf.get('amqpvhost', '/zenoss')
port = int(global_conf.get('amqpport', '5672'))
host = global_conf.get('amqphost', 'localhost')

ROUTERS = {'EventsRouter': 'evconsole',}

class ZenossAPI():
    def __init__(self, debug=False):
        """
        Initialize the API connection, log in, and store authentication cookie
        """
        # Use the HTTPCookieProcessor as urllib2 does not save cookies by default
        self.urlOpener = urllib2.build_opener(urllib2.HTTPCookieProcessor())
        if debug: self.urlOpener.add_handler(urllib2.HTTPHandler(debuglevel=1))
        self.reqCount = 1

        # Contruct POST params and submit login.
        loginParams = urllib.urlencode(dict(
                        __ac_name = zenuser,
                        __ac_password = zenpass,
                        submitted = 'true',
                        came_from = destinationHost + '/zport/dmd'))
        self.urlOpener.open(destinationHost + '/zport/acl_users/cookieAuthHelper/login',
                            loginParams)

    def _router_request(self, router, method, data=[]):
        if router not in ROUTERS:
            raise Exception('Router "' + router + '" not available.')

        # Contruct a standard URL request for API calls
        req = urllib2.Request(destinationHost + '/zport/dmd/' +
                              ROUTERS[router] + '_router')

        # NOTE: Content-type MUST be set to 'application/json' for these requests
        req.add_header('Content-type', 'application/json; charset=utf-8')

        # Convert the request parameters into JSON
        reqData = json.dumps([dict(
                    action=router,
                    method=method,
                    data=data,
                    type='rpc',
                    tid=self.reqCount)])

        # Increment the request count ('tid'). More important if sending multiple
        # calls in a single request
        self.reqCount += 1
        # Submit the request and convert the returned JSON to objects
        return json.loads(self.urlOpener.open(req, reqData).read())


    def createEvent(self, device, severity, summary, evclass):
        if severity not in ('Critical', 'Error', 'Warning', 'Info', 'Debug', 'Clear'):
            raise Exception('Severity "' + severity +'" is not valid.')

        data = dict(device=device, summary=summary, severity=severity,
                    component='', evclasskey='', evclass=evclass)
        return self._router_request('EventsRouter', 'add_event', [data])


class ZEFPrefs(object):
    zope.interface.implements(ICollectorPreferences)

    def __init__(self):
        """
        Constructs a new ColPrefs instance and
        provides default values for needed attributes.
        """
        self.collectorName = COLLECTOR_NAME
        self.defaultRRDCreateCommand = None
        self.configCycleInterval = 20 # minutes
        self.cycleInterval = 5 * 60 # seconds

        # The configurationService attribute is the fully qualified class-name
        # of our configuration service that runs within ZenHub
        self.configurationService = 'ZenPacks.SteelHouseLabs.ZenossForwarder.services.ZEFService'

        # Will be filled in based on buildOptions
        self.options = None

        self.configCycleInterval = 20*60

    def postStartupTasks(self):
        task = ZEFTask(COLLECTOR_NAME, configId=COLLECTOR_NAME)
        yield task

    def buildOptions(self, parser):
        """
        Command-line options to be supported
        """
        pass


    def postStartup(self):
        daemon = zope.component.getUtility(ICollector)
        
        # add our collector's custom statistics
        statService = zope.component.queryUtility(IStatisticsService)
        statService.addStatistic("events", "COUNTER")


class ZEFTask(BaseTask):
    """
    Consume the eventForwarder queue for messages and turn them into events
    """
    zope.interface.implements(IScheduledTask)

    DATE_FORMAT = '%b %d %H:%M:%S'
    SAMPLE_DATE = 'Apr 10 15:19:22'

    log.info('Settting up JSON API...')
    jsonAPI = ZenossAPI()

    log.info('Setting up AMQP...')
    credentials = pika.PlainCredentials(user, passwd)

    connection = pika.BlockingConnection(pika.ConnectionParameters(host = host,
                                             port = port,
                                             virtual_host = vhost,
                                             credentials = credentials))

    channel = connection.channel()

    channel.queue_bind(exchange='events',
                        queue=queue)


    def __init__(self, taskName, configId,
                 scheduleIntervalSeconds=3600, taskConfig=None):
        BaseTask.__init__(self, taskName, configId,
                 scheduleIntervalSeconds, taskConfig)

        self.log = log

        # Needed for ZCA interface
        self.name = taskName
        self.configId = configId
        self.state = TaskStates.STATE_IDLE
        self.interval = scheduleIntervalSeconds
        self._preferences = taskConfig
        self._daemon = zope.component.getUtility(ICollector)
        self._eventService = zope.component.queryUtility(IEventService)
        self._statService = zope.component.queryUtility(IStatisticsService)
        self._preferences = self._daemon

        self.options = self._daemon.options

        self._daemon.changeUser()
        self.processor = None

        log.info('Starting AMQP consumption...')
        self.channel.basic_consume(self.callback,
                              queue=queue,
                              no_ack=True)

        self.channel.start_consuming()


    def callback(self, ch, method, properties, body):
        self.log.debug(" [EVENT] %s" % (body,))
        self.passEvent(body)


    def passEvent(self, evtBody):
        sevStrings={5:'Critical', 4:'Error', 3:'Warning', 2:'Info', 0:'Clear', 1:'Debug'}
        evt = eval(evtBody)
        self.jsonAPI.createEvent(device=str(evt['element_title']), summary=str(evt['summary']), evclass=str(evt['event_class']), severity=str(evt[evString[int('severity')]]))


    def doTask(self):
        """
        This is a wait-around task since we really are called
        asynchronously.
        """
        return defer.succeed("Waiting for messages...")

    def cleanup(self):
        self.log.info('cleanup')


    @defer.inlineCallbacks
    def _shutdown(self, *ignored):
        self.log.info("Shutting down...")
        self.log.info("Closing log...")
        self.dataLog.close()
        self.log.info("Closing AMQP connection...")
        self.channel.close()
        self.connection.close()


class ZEFConf(ObservableMixin):
    """
    Receive a configuration object
    """
    zope.interface.implements(IScheduledTask)

    def __init__(self, taskName, configId,
                 scheduleIntervalSeconds=3600, taskConfig=None):
        super(ZEFConf, self).__init__()

        # Needed for ZCA interface
        self.name = taskName
        self.configId = configId
        self.state = TaskStates.STATE_IDLE
        self.interval = scheduleIntervalSeconds
        self._preferences = taskConfig
        self._daemon = zope.component.getUtility(ICollector)


    def doTask(self):
        return defer.succeed("Success")

    def cleanup(self, body):
        pass

class ZEFDaemon(CollectorDaemon):
   pass

if __name__=='__main__':
    Preferences = ZEFPrefs()
    TaskFactory = SimpleTaskFactory(ZEFConf)
    TaskSplitter = SimpleTaskSplitter(TaskFactory)
    zef = ZEFDaemon(Preferences, TaskSplitter)
    zef.run()
