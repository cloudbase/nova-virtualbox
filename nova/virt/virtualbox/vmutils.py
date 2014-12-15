# Copyright (c) 2015 Cloudbase Solutions Srl
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Helper methods for operations related to the management of virtual
machines records and their settings.
"""

import time

from eventlet import timeout as etimeout
from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils

from nova import exception as nova_exception
from nova import i18n
from nova.openstack.common import loopingcall
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception
from nova.virt.virtualbox import manage

LOG = logging.getLogger(__name__)
VIRTUAL_BOX = [
    cfg.IntOpt('wait_soft_reboot_seconds',
               default=60,
               help='Number of seconds to wait for instance to shut down'
                    'after soft reboot request is made.'),
]
CONF = cfg.CONF
CONF.register_opts(VIRTUAL_BOX, 'virtualbox')


def wait_for_power_state(instance, power_state, time_limit):
    """Waiting for a virtual machine to be in required power state.

    :param instance:    nova.objects.instance.Instance
    :param power_state: nova.compute.power_state
    :param time_limit:  (int) time limit for this task

    :return: True if the instance is in required power state
             within time_limit, False otherwise.
    """

    def _check_power_state(instance):
        current_state = get_power_state(instance)
        LOG.debug("Wait for soft shutdown: (%s, %s)", current_state,
                  power_state)
        if current_state == power_state:
            raise loopingcall.LoopingCallDone()
    response = True
    periodic_call = loopingcall.FixedIntervalLoopingCall(_check_power_state,
                                                         instance)
    try:
        # add a timeout to the periodic call.
        periodic_call.start(interval=constants.SHUTDOWN_RETRY_INTERVAL)
        etimeout.with_timeout(time_limit, periodic_call.wait)
    except etimeout.Timeout:
        # Virtual machine did not shutdown in the expected time_limit.
        response = False

    finally:
        # Stop the periodic call, in case of exceptions or Timeout.
        periodic_call.stop()

    return response


def get_host_info():
    """Get information regarding host.

    Returns a dict containing:
        :HOST_PROCESSOR_COUNT:          (int) Processor count
        :HOST_PROCESSOR_CORE_COUNT:     (int) Processor core count
        :HOST_MEMORY_AVAILABLE:         (int) Available memory in MB
        :HOST_MEMORY_SIZE:              (int) Memory size in MB
    """
    output = manage.VBoxManage.list(constants.HOST_INFO)
    information = {}

    for line in output.splitlines():
        if not line:
            continue
        key, _, value = line.partition(':')
        key = key.strip()
        if key in (constants.HOST_PROCESSOR_COUNT,
                   constants.HOST_PROCESSOR_CORE_COUNT):
            try:
                information[key] = int(value.strip())
            except ValueError:
                information[key] = 0

        elif key in (constants.HOST_MEMORY_AVAILABLE,
                     constants.HOST_MEMORY_SIZE):
            try:
                information[key] = int(value.strip().split()[0])
            except ValueError:
                information[key] = 0

    return information


def get_os_types():
    """Return a list with all guest operating systems presently known
    to VirtualBox, along with the identifiers used to refer to them
    with the modify_vm command.
    """
    output = manage.VBoxManage.list(constants.OSTYPES_INFO)
    os_types = []

    for line in output.splitlines():
        if not line:
            continue
        key, _, value = line.partition(':')
        if key.strip() == "ID":
            os_types.append(value.strip())

    return os_types


def get_power_state(instance):
    """Return the power state of the received instance.

    :param instance: nova.objects.instance.Instance
    :return: nova.compute.power_state
    """
    instance_info = manage.VBoxManage.show_vm_info(instance)
    return instance_info.get(constants.VM_POWER_STATE)


def set_cpus(instance):
    """Set the number of virtual CPUs for the virtual machine.

    :param instance: nova.objects.instance.Instance
    """
    host_info = get_host_info()
    if instance.vcpus > host_info[constants.HOST_PROCESSOR_COUNT]:
        raise nova_exception.ImageNUMATopologyCPUOutOfRange(
            cpunum=instance.vcpus,
            cpumax=host_info[constants.HOST_PROCESSOR_COUNT])

    manage.VBoxManage.modify_vm(instance, constants.FIELD_CPUS,
                                instance.vcpus)


def set_memory(instance):
    """Set the amount of RAM, in MB, that the virtual machine
    should allocate for itself from the host.

    :param instance: nova.objects.instance.Instance
    """
    host_info = get_host_info()
    if instance.memory_mb > host_info[constants.HOST_MEMORY_AVAILABLE]:
        raise nova_exception.InsufficientFreeMemory(uuid=instance.uuid)

    manage.VBoxManage.modify_vm(instance, constants.FIELD_MEMORY,
                                instance.memory_mb)


def set_os_type(instance, os_type):
    """Specifies what guest operating system is supposed to run
    in the virtual machine.

    :param instance: nova.objects.instance.Instance
    :param os_type: guest operating system
    """
    all_os_types = get_os_types()
    if os_type not in all_os_types:
        LOG.warning("Unknown os type %s, assuming %s",
                    os_type, constants.DEFAULT_OS_TYPE)
        os_type = constants.DEFAULT_OS_TYPE

    manage.VBoxManage.modify_vm(instance, constants.FIELD_OS_TYPE, os_type)


def set_storage_controller(instance, system_bus, controller=None,
                           name=None):
    """Attaches a storage controller to the instance.

    :param instance:    nova.objects.instance.Instance
    :param name:        name of the storage controller.
    :param system_bus:  type of the system bus to which the storage
                        controller must be connected.
    :param controller:  type of chipset being emulated for the given
                        storage controller.
    """
    if system_bus == constants.SYSTEM_BUS_SCSI:
        name = constants.DEFAULT_SCSI_CNAME
        controller = controller or constants.DEFAULT_SCSI_CONTROLLER

    elif system_bus == constants.SYSTEM_BUS_SATA:
        name = constants.DEFAULT_SATA_CNAME
        controller = controller or constants.DEFAULT_SATA_CONTROLLER

    elif system_bus == constants.SYSTEM_BUS_IDE:
        name = constants.DEFAULT_IDE_CNAME
        controller = controller or constants.DEFAULT_IDE_CONTROLLER

    return manage.VBoxManage.storage_ctl(instance, name, system_bus,
                                         controller)


def update_description(instance, description):
    """Update description for received instance."""
    instance_info = manage.VBoxManage.show_vm_info(instance)
    current_description = instance_info.get('current_description', {})

    if current_description:
        try:
            current_description = jsonutils.loads(current_description)
        except ValueError:
            current_description = {}

    current_description.update(description)

    manage.VBoxManage.modify_vm(instance, constants.FIELD_DESCRIPTION,
                                jsonutils.dumps(current_description))


def soft_shutdown(instance, timeout=0, retry_interval=0):
    """If ACPI is available for this instance the ACPI shutdown button
    will be pressed.

    :param instance:       nova.objects.instance.Instance
    :param timeout:        time to wait for GuestOS to shutdown
    :param retry_interval: how often to signal guest while waiting
                           for it to shutdown

    .. note:
        We fall back to hard reboot if instance does not shutdown
        within this window.
    """
    if timeout <= 0:
        LOG.debug("No timeout provided, assuming %d",
                  CONF.virtualbox.wait_soft_reboot_seconds)
        timeout = CONF.virtualbox.wait_soft_reboot_seconds

    if retry_interval <= 0:
        LOG.debug("No retry_interval provided, assuming %d",
                  constants.SHUTDOWN_RETRY_INTERVAL)
        retry_interval = constants.SHUTDOWN_RETRY_INTERVAL

    instance_info = manage.VBoxManage.show_vm_info(instance)
    desired_power_state = constants.STATE_POWER_OFF

    if not instance_info.get(constants.VM_ACPI, 'off') == 'on':
        return False

    LOG.debug("Performing soft shutdown on instance", instance=instance)
    while timeout > 0:
        wait_time = min(retry_interval, timeout)
        try:
            LOG.debug("Soft shutdown instance, timeout remaining: %d",
                      timeout, instance=instance)
            try:
                manage.VBoxManage.control_vm(instance,
                                             constants.ACPI_POWER_BUTTON)
            except nova_exception.InstanceInvalidState:
                if get_power_state(instance) == desired_power_state:
                    LOG.info(i18n._LI("Soft shutdown succeeded."),
                             instance=instance)
                    return True
                raise

            if wait_for_power_state(instance, desired_power_state, wait_time):
                LOG.info(i18n._LI("Soft shutdown succeeded."),
                         instance=instance)
                return True

        except exception.VBoxException as exc:
            LOG.debug("Soft shutdown failed: %s", exc, instance=instance)
            time.sleep(wait_time)

        timeout -= retry_interval

    LOG.warning(i18n._LW("Timed out while waiting for soft shutdown."),
                instance=instance)
    return False
