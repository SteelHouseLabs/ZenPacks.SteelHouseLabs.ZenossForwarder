===============================================================================
ZenPacks.SteelHouseLabs.ZenossForwarder
===============================================================================


About
-------------------------------------------------------------------------------
Forwards events from one Zenoss to another.


Features
-------------------------------------------------------------------------------
This ZenPack reads events from the eventForwarder queue and forwards them via
JSON to a configured target Zenoss instance


Prerequisites
-------------------------------------------------------------------------------

==================  =========================================================
Prerequisite        Restriction
==================  =========================================================
Product             Zenoss 4.1.1 or higher
Required ZenPacks   ZenPacks.SteelHouseLabs.EventForwarder
Other dependencies  pika 0.98
==================  =========================================================


Limitations
-------------------------------------------------------------------------------
These notification actions are not able to provide immediate feedback as to
whether or not configuration information is correct, so the ``zenactiond.log``
file must be checked to ensure that the actions are working correctly.


Usage
-------------------------------------------------------------------------------
See the Zenoss Service Dynamics Administration Guide for more information about
triggers and notifications. Any issues detected during the run of the
notification will result in an event sent to the event console as well as a
message in the ``zenactiond.log`` file. The ``zenossforwarder.log`` file will
contain a s log of streamed messages.


Select the Event Forwarder Action
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This assumes that the appropriate triggers have already been set up.

1. Navigate to ``Events`` -> ``Triggers`` page.

2. Click on the ``Notifications`` menu item.

3. Click on the plus sign ('+') to add a new notification.

4. From the dialog box, specify the name of the notification and select the
   ``Event Forwarder`` action.

5. Enable the notification and add a trigger to be associated with this action.

6. Click on the ``Submit`` button.


Installing
-------------------------------------------------------------------------------

Install the ZenPack via the command line and restart Zenoss::

NOTE: DO NOT link install EventForwarder or ZenossForwarder!

    easy_install pika
    zenpack --install ZenPacks.SteelHouseLabs.EventForwarder-<version>.egg
    zenpack --install ZenPacks.SteelHouseLabs.ZenossForwarder-<version>.egg
    zenoss restart


Removing
-------------------------------------------------------------------------------

To remove the ZenPack, use the following command::

NOTE: Remove any configuration changes for ZenossForwarder configured in $ZENHOME/etc/global.conf
NOTE: Add zenforwarder to daemons.txt

    zenpack --remove ZenPacks.SteelHouseLabs.EventForwarder
    zenpack --remove ZenPacks.SteelHouseLabs.ZenossForwarder
    
    zenoss restart
    
    
Configuration
-------------------------------------------------------------------------------

$ZENHOME/etc/global.conf

=============================  ==========================================================
Parameter                      Description
=============================  ==========================================================
zenforwarderDestinationUrl     Target Zenoss instance. Example: http://10.0.0.2:8080
zenuser                        Target Zenoss instance user who can write to JSON
zenpass                        Target Zenoss instance user password who can write to JSON
=============================  ==========================================================

Troubleshooting
-------------------------------------------------------------------------------

The Zenoss support team will need the following output:

1. Set the ``zenhub`` daemon into ``DEBUG`` level logging by typing
   ``zenhub debug`` from the command-line. This will ensure that we can see the
   incoming event in the ``zenhub.log`` file.

2. Set the ``zenactiond`` daemon into ``DEBUG`` level logging by typing
   ``zenactiond debug`` from the command-line. This will ensure that we can see
   the incoming notification request and processing activity in the
   ``zenactiond.log`` file.

3. Create an event from the remote source, by the ``zensendevent`` command or by
   the event console ``Add an Event`` button. This event must match the trigger
   definition that will invoke your notification action.

4. Verify that the event was processed by the ``zenhub`` daemon by examining the
   ``zenhub.log`` file.

5. Wait for the ``zenactiond`` daemon to receive and then process the
   notification request.

6. In the case of errors an event will be generated and sent to the event
   console.

7. Running rabbitmqctl -p /zenoss list_queues should show a 'eventForwarder' queue 
once after the Notification is enabled on the Triggers -> Notifications page.

8. Verify pika >= 0.98 is installed


Appendix Related Daemons
-------------------------------------------------------------------------------

============  ===============================================================
Type          Name
============  ===============================================================
Notification  zenactiond
============  ===============================================================
Forwarder     zenforwarder
============  ===============================================================

