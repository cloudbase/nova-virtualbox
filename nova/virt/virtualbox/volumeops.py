# Copyright 2015 Cloudbase Solutions Srl
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
Management class for operations related to the storage.
"""

import platform

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils

from nova import exception
from nova.i18n import _LE, _LW
from nova.virt import driver
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exc
from nova.virt.virtualbox import manage
from nova.virt.virtualbox import vhdutils
from nova.virt.virtualbox import volumeutils


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CONF.import_opt('my_ip', 'nova.netconf')


class VolumeOperations(object):

    def __init__(self):
        self._vbox_manage = manage.VBoxManage()
        self.volume_drivers = {'iscsi': ISCSIVolumeDriver()}
        self._initiator = None

    def _get_volume_driver(self, driver_type=None, connection_info=None):
        """Get the required driver for this type of storage."""
        if connection_info:
            driver_type = connection_info.get('driver_volume_type')

        if driver_type not in self.volume_drivers:
            raise exception.VolumeDriverNotFound(driver_type=driver_type)

        LOG.debug("The volume driver was found: %(driver)s.",
                  {"driver": driver_type})
        return self.volume_drivers[driver_type]

    def get_volume_connector(self, instance):
        """Get connector information for the instance for attaching to
        volumes.
        """
        if not self._initiator:
            self._initiator = self.volume_drivers["iscsi"].get_initiator(
                instance)

        volume_connector = {
            'ip': CONF.my_ip,
            'host': platform.node(),
            'initiator': self._initiator,
        }

        LOG.debug("Volume connector: %(volume_connector)s",
                  {"volume_connector": volume_connector})
        return volume_connector

    def attach_volumes(self, instance, block_device_info, ebs_root):
        """Attach volumes to the properly storage controller."""
        mapping = driver.block_device_info_get_mapping(block_device_info)

        if ebs_root:
            self.attach_volume(instance, mapping[0]['connection_info'],
                               True)
            mapping = mapping[1:]
        for vol in mapping:
            self.attach_volume(instance, vol['connection_info'])

    def attach_volume(self, instance, connection_info, ebs_root=False):
        """Attach volume using the volume driver."""
        volume_driver = self._get_volume_driver(
            connection_info=connection_info)
        volume_driver.attach_volume(instance, connection_info, ebs_root)

    def detach_volume(self, instance, connection_info):
        """Detach volume using the volume driver."""
        volume_driver = self._get_volume_driver(
            connection_info=connection_info)
        volume_driver.detach_volume(instance, connection_info)

    def attach_storage(self, instance, controller, port, device, drive_type,
                       medium):
        """Attach a storage medium connected to a storage controller.

        :param instance:   nova.objects.instance.Instance
        :param controller: name of the storage controller.
        :param port:       the number of the storage controller's port
                           which is to be modified.
        :param device:     the number of the port's device which is to
                           be modified.
        :param drive_type: define the type of the drive to which the
                           medium is being attached.
        :param medium:     specifies what is to be attached
        """
        return self._vbox_manage.storage_attach(
            instance, controller, port, device, drive_type, medium)


class ISCSIVolumeDriver(object):

    """ISCSI Volume Driver."""

    def __init__(self):
        self._vbox_manage = manage.VBoxManage()

    def get_initiator(self, instance):
        """Return the iSCSI Initiator name."""
        # TODO(alexandrucoman): Try to get the builtin iSCSI initiator
        initiator = "iqn.2008-04.com.sun:{host}".format(host=platform.node())
        LOG.debug("iSCSI Initiator Name: %(initiator)s",
                  {"initiator": initiator}, instance=instance)
        return initiator

    def attach_volume(self, instance, connection_info, ebs_root=False):
        """Attach a volume to the SCSI controller or to the SATA controller if
        ebs_root is True.

        .. notes:
            This action require the instance to be powered off
        """
        LOG.debug("Attach_volume: %(connection_info)s to %(instance_name)s",
                  {'connection_info': connection_info,
                   'instance_name': instance.name})

        if ebs_root:
            # Attaching to the first slot of SATA controller
            controller = constants.SYSTEM_BUS_SATA.upper()
            port, device = (0, 0)
        else:
            # Attaching to the first available port of SCSI controller
            controller = constants.SYSTEM_BUS_SCSI.upper()
            port, device = vhdutils.get_available_attach_point(instance,
                                                               controller)
        try:
            self._vbox_manage.scsi_storage_attach(
                instance, controller, port, device, connection_info,
                self.get_initiator(instance))
        except (vbox_exc.VBoxException, exception.InstanceInvalidState) as exc:
            with excutils.save_and_reraise_exception():
                LOG.error(_LE("Unable to attach volume to "
                              "instance %(instance)s: %(reason)s"),
                          {"instance": instance.name, "reason": exc})
                self.detach_volume(instance, connection_info)

    def detach_volume(self, instance, connection_info):
        """Detach a volume to the SCSI controller.

        .. notes:
            This action require the instance to be powered off
        """
        LOG.debug("Detach_volume: %(connection_info)s from %(instance_name)s",
                  {'connection_info': connection_info,
                   'instance_name': instance.name})
        volume_uuid = volumeutils.volume_uuid(connection_info)
        if not volume_uuid:
            LOG.warning(
                _LW("The volume %(connection_info)s is not registered."),
                {"connection_info": connection_info})
            return

        try:
            device, port = vhdutils.get_attach_point(
                instance, constants.SYSTEM_BUS_SCSI.upper(), volume_uuid)
        except TypeError:
            LOG.warning(
                _LW("Fail to get attach point for %(volume_uuid)s"),
                {"volume_uuid": volume_uuid})
            self._vbox_manage.close_medium(constants.MEDIUM_DISK, volume_uuid)
            return

        try:
            self._vbox_manage.storage_attach(
                instance, constants.SYSTEM_BUS_SCSI.upper(), port, device,
                drive_type=constants.STORAGE_HDD,
                medium=constants.MEDIUM_NONE)
            self._vbox_manage.close_medium(constants.MEDIUM_DISK, volume_uuid)
        except (vbox_exc.VBoxException, exception.InstanceInvalidState) as exc:
            with excutils.save_and_reraise_exception():
                LOG.error(_LE("Unable to attach volume to "
                              "instance %(instance)s: %(reason)s"),
                          {"instance": instance.name, "reason": exc})
