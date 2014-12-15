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
Management class for migration / resize operations.
"""

import os
import shutil

from oslo_log import log as logging
from oslo_utils import excutils
from oslo_utils import units

from nova import exception
from nova import i18n
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exc
from nova.virt.virtualbox import hostutils
from nova.virt.virtualbox import imagecache
from nova.virt.virtualbox import manage
from nova.virt.virtualbox import pathutils
from nova.virt.virtualbox import vhdutils
from nova.virt.virtualbox import vmops
from nova.virt.virtualbox import volumeutils

LOG = logging.getLogger(__name__)


class MigrationOperations(object):

    """Management class for migration operations."""

    _SUFFIX = "_copy"

    def __init__(self):
        self._vbox_manage = manage.VBoxManage()
        self._vbox_ops = vmops.VBoxOperation()

    def _detach_storage(self, instance):
        """Detach all disks and volumes attached to the current instance.

        Return a list with all disks detached.
        """
        disks = []
        for controller in vhdutils.get_controllers(instance):
            for attach_point, disk in controller.items():
                if not disk['path']:
                    continue

                LOG.debug("Trying to detach %(disk)s from %(controller)s: "
                          "%(attach_point)s",
                          {"disk": disk, "controller": controller,
                           "attach_point": attach_point})
                try:
                    self._vbox_manage.storage_attach(
                        instance, controller,
                        port=attach_point[0], device=attach_point[1],
                        drive_type=constants.STORAGE_HDD,
                        medium=constants.MEDIUM_NONE,
                    )
                except vbox_exc.VBoxException as exc:
                    LOG.warning(i18n._LW("Failed to detach distk %(disk)s: "
                                         "%(reason)s"),
                                         {"disk": disk, "reason": exc})

                if '|' in disk["path"]:
                    LOG.debug("Trying to unregister %(path)s",
                              {"path": disk["path"]})
                    self._vbox_manage.close_medium(constants.MEDIUM_DISK,
                                                   disk["path"])
                else:
                    disks.append(disk)

        return disks

    def _remove_disks(self, path):
        for disk_file in os.listdir(path):
            disk_path = os.path.join(path, disk_file)
            try:
                LOG.debug("Trying to unregister %(path)s", {"path": disk_path})
                self._vbox_manage.close_medium(
                    constants.MEDIUM_DISK, disk_path, delete=True)
            except vbox_exc.VBoxException:
                LOG.debug("Remove file: %(path)s", {"path": disk_path})
                pathutils.delete_path(disk_path)

    def _check_disk(self, disk_file, base_disk):
        try:
            vhdutils.check_disk_uuid(disk_file)
            disk_info = vhdutils.disk_info(disk_file)
            parent_uuid = disk_info[constants.VHD_PARENT_UUID]
            if not parent_uuid:
                return
        except vbox_exc.VBoxException:
            parent_uuid = None

        registered_hdds = vhdutils.get_hard_disks()
        if parent_uuid not in registered_hdds:
            parent_info = vhdutils.disk_info(base_disk)
            self._vbox_manage.set_disk_parent_uuid(
                disk_file, parent_info[constants.VHD_UUID])

    def _cleanup_failed_disk_migration(self, instance_path,
                                       revert_path, dest_path):
        if dest_path and os.path.exists(dest_path):
            self._remove_disks(dest_path)
            pathutils.delete_path(dest_path)

        if revert_path and os.path.exists(revert_path):
            os.rename(revert_path, instance_path)

    def _revert_migration_files(self, instance):
        instance_basepath = pathutils.instance_basepath(instance)
        revert_path = pathutils.revert_dir(instance)
        os.rename(revert_path, instance_basepath)

    def _migrate_disk(self, disk_file, destination, root_disk=False):
        disk_info = vhdutils.disk_info(disk_file)
        disk_format = disk_info[constants.VHD_IMAGE_TYPE]

        if root_disk:
            dest_file = os.path.join(destination,
                                     "root." + disk_format.lower())
        else:
            dest_file = os.path.join(destination,
                                     os.path.basename(disk_file))

        if not disk_info[constants.VHD_PARENT_UUID]:
            self._vbox_manage.clone_hd(disk_file, dest_file, disk_format)
        else:
            shutil.copy(disk_file, dest_file)

    def _migrate_disk_files(self, instance, disk_files, destination):
        local_ips = hostutils.get_local_ips()
        local_ips.append(hostutils.get_ip())
        same_host = destination in local_ips
        LOG.debug("Destination `%(dest)s` %(local_ips)s",
                  {"dest": destination, "local_ips": local_ips})

        instance_basepath = pathutils.instance_basepath(instance)
        revert_path = pathutils.revert_dir(
            instance, action=constants.PATH_OVERWRITE)

        if same_host:
            destination_path = (
                "%(path)s%(suffix)s" %
                {"path": instance_basepath, "suffix": self._SUFFIX})
        else:
            LOG.warning(
                i18n._LW("Only resize on the same host is supported!"))
            raise NotImplementedError()

        # Delete the destination path if already exists
        pathutils.delete_path(destination_path)

        # Create the destination path
        pathutils.create_path(destination_path)

        try:
            self._migrate_disk(disk_files[0], destination_path, root_disk=True)
            for disk_file in disk_files[1:]:
                self._migrate_disk(disk_file, destination_path)

            # Remove the instance from the Hypervisor
            self._vbox_ops.destroy(instance, destroy_disks=False)

            # Move files to revert path
            os.rename(instance_basepath, revert_path)
            if same_host:
                os.rename(destination_path, instance_basepath)
        except (OSError, vbox_exc.VBoxException):
            with excutils.save_and_reraise_exception():
                try:
                    self._cleanup_failed_disk_migration(
                        instance_basepath, revert_path, destination_path)
                except vbox_exc.VBoxException as exc:
                    # Log and ignore this exception
                    LOG.exception(exc)

    def _resize_disk(self, instance, new_size, disk_file):
        if not new_size:
            return
        disk_info = vhdutils.disk_info(disk_file)
        current_size = disk_info[constants.VHD_CAPACITY] / units.Mi
        if vhdutils.is_resize_required(disk_file, current_size,
                                       new_size, instance):
            self._vbox_manage.modify_hd(
                disk_file, constants.FIELD_HD_RESIZE_MB, new_size)

    def migrate_disk_and_power_off(self, context, instance, dest, flavor,
                                   network_info, block_device_info=None,
                                   timeout=0, retry_interval=0):
        """Transfers the disk of a running instance in multiple phases, turning
        off the instance before the end.
        """
        LOG.debug("`Migrate disk and power off` method called.",
                  instance=instance)
        # Power off the instance
        self._vbox_ops.power_off(instance, timeout, retry_interval)

        # Check if resize is posible
        if flavor['root_gb'] < instance['root_gb']:
            raise exception.InstanceFaultRollback(
                i18n._("Cannot resize the root disk to a smaller size. "
                       "Current size: %(current_size)s GB. Requested size: "
                       "%(new_size)s GB") %
                {'current_size': instance['root_gb'],
                 'new_size': flavor['root_gb']})

        # Migrate the disks
        disks = self._detach_storage(instance)
        if disks:
            self._migrate_disk_files(instance, disks, dest)

    def finish_revert_migration(self, context, instance, network_info,
                                block_device_info=None):
        """Finish reverting a resize."""
        LOG.debug("`Finish revert migration` method called.")
        self._revert_migration_files(instance)
        self._vbox_ops.create_instance(instance, image_meta={},
                                       network_info=network_info,
                                       overwrite=False)

        if volumeutils.ebs_root_in_block_devices(block_device_info):
            root_path = None
        else:
            root_path = pathutils.lookup_root_vhd_path(instance)
        eph_path = pathutils.lookup_ephemeral_vhd_path(instance)

        self._vbox_ops.storage_setup(instance, root_path, eph_path,
                                     block_device_info)

    def confirm_migration(self, migration, instance, network_info):
        """Confirms a resize, destroying the source VM."""
        LOG.debug("`Confirms migration` method called.")
        revert_path = pathutils.revert_dir(instance)
        self._remove_disks(revert_path)
        pathutils.delete_path(revert_path)

    def finish_migration(self, context, migration, instance, disk_info,
                         network_info, image_meta, resize_instance=False,
                         block_device_info=None):
        """Completes a resize."""
        LOG.debug("`Finish migration` method called.")
        if volumeutils.ebs_root_in_block_devices(block_device_info):
            root_path = None
        else:
            root_path = pathutils.lookup_root_vhd_path(instance)
            if not root_path:
                raise vbox_exc.VBoxException(
                    i18n._("Cannot find boot VHD file for instance: %s") %
                    instance.name)
            base_disk_path = imagecache.get_cached_image(context, instance)
            self._check_disk(root_path, base_disk_path)

        ephemeral_path = pathutils.lookup_ephemeral_vhd_path(instance)
        if not ephemeral_path:
            ephemeral_path = self._vbox_ops.create_ephemeral_disk(instance)

        if resize_instance:
            self._resize_disk(instance, instance.root_gb * units.Ki, root_path)
            self._resize_disk(instance,
                              instance.get('ephemeral_gb', 0) * units.Ki,
                              ephemeral_path)

        self._vbox_ops.create_instance(instance, image_meta, network_info,
                                       overwrite=False)
        self._vbox_ops.storage_setup(instance, root_path, ephemeral_path,
                                     block_device_info)
