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
Management class for operations related to snapshots.
"""
import os
import time

from oslo_utils import excutils
from oslo_log import log as logging

from nova.compute import task_states
from nova import i18n
from nova.image import glance
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception
from nova.virt.virtualbox import manage
from nova.virt.virtualbox import pathutils
from nova.virt.virtualbox import vhdutils

LOG = logging.getLogger(__name__)


class SnapshotOperations(object):

    """Management class for operation related to snapshots."""

    def __init__(self):
        self._vbox_manage = manage.VBoxManage()

    def _clenup_disk(self, disk):
        LOG.debug('Trying to close and remove the disk %(disk)s if exists.',
                  {"disk": disk})
        if disk and os.path.exists(disk):
            try:
                self._vbox_manage.close_medium(constants.MEDIUM_DISK, disk)
            except exception.VBoxManageError as error:
                LOG.warning(i18n._LW("Failed to remove %(disk)s: %(reason)s"),
                            {"disk": disk, "reason": error})
            pathutils.delete_path(disk)

    def _save_glance_image(self, context, image_id, image_vhd_path):
        LOG.debug("Updating Glance image %(image_id)s with content from "
                  "merged disk %(image_vhd_path)s",
                  {'image_id': image_id, 'image_vhd_path': image_vhd_path})

        disk_format = vhdutils.get_image_type(image_vhd_path)
        (glance_image_service,
         image_id) = glance.get_remote_image_service(context, image_id)
        image_metadata = {"is_public": False,
                          "disk_format": disk_format.lower(),
                          "container_format": "bare",
                          "properties": {}}

        with open(image_vhd_path, 'rb') as file_handle:
            glance_image_service.update(context, image_id, image_metadata,
                                        file_handle)

    def _export_disk(self, instance):
        LOG.debug("Trying to get the root virtual hard driver.")
        current_disk = pathutils.get_root_disk_path(instance)
        if not current_disk:
            raise exception.VBoxException("Cannot get the root disk.")

        disk_info = vhdutils.disk_info(current_disk)
        root_disk_uuid = disk_info[constants.VHD_PARENT_UUID]
        root_disk = vhdutils.disk_info(root_disk_uuid)

        # The root virtual disk is a base disk
        root_disk_path = root_disk[constants.VHD_PATH]
        export_path = os.path.join(
            pathutils.export_dir(instance, constants.PATH_CREATE),
            os.path.basename(root_disk_path))

        LOG.debug("Trying to export the virtual disk to %(export_path)s.",
                  {"export_path": export_path})
        existing = constants.VHD_PARENT_UUID in root_disk
        if existing:
            # The root virtual disk is linked to another disk
            base_info = vhdutils.disk_info(
                root_disk[constants.VHD_PARENT_UUID])
            base_disk_path = base_info[constants.VHD_PATH]
            try:
                LOG.debug("Cloning base disk for the root disk.")
                self._vbox_manage.clone_hd(
                    vhd_path=base_disk_path,
                    new_vdh_path=export_path,
                    disk_format=root_disk[constants.VHD_IMAGE_TYPE])
            except exception.VBoxException:
                with excutils.save_and_reraise_exception():
                    self._clenup_disk(export_path)

        try:
            LOG.debug(
                "Cloning VHD image %(base)s to target: %(target)s",
                {'base': root_disk_path, 'target': export_path})

            # Note(alexandrucoman): If the target disk already exists
            # only the portion of the source medium which fits into the
            # destination medium is copied.
            # This means if the destination medium is smaller than the
            # source only a part of it is copied, and if the destination
            # medium is larger than the source the remaining part of the
            # destination medium is unchanged.
            self._vbox_manage.clone_hd(root_disk_path, export_path,
                                       existing=existing)
        except exception.VBoxException:
            with excutils.save_and_reraise_exception():
                self._clenup_disk(export_path)

        return export_path

    def take_snapshot(self, context, instance, image_id, update_task_state):
        """Take a snapshot of the current state of the virtual machine."""
        snapshot_name = "Snapshot-%(timestamp)s" % {"timestamp": time.time()}
        LOG.debug("Creating snapshot %(name)s for instance %(instance)s",
                  {'instance': instance.name, 'name': snapshot_name})
        self._vbox_manage.take_snapshot(instance, snapshot_name, live=True)
        update_task_state(task_state=task_states.IMAGE_PENDING_UPLOAD)
        export_path = None
        try:
            export_path = self._export_disk(instance)
            update_task_state(task_state=task_states.IMAGE_UPLOADING,
                              expected_state=task_states.IMAGE_PENDING_UPLOAD)
            self._save_glance_image(context, image_id, export_path)
            LOG.debug("Snapshot image %(image_id)s updated for VM "
                      "%(instance_name)s",
                      {'image_id': image_id, 'instance_name': instance.name})
        finally:
            try:
                LOG.debug("Removing snapshot %s", image_id)
                self._vbox_manage.delete_snapshot(instance, snapshot_name)
            except exception.VBoxManageError as exc:
                LOG.warning(i18n._LW("Failed to remove snapshot for"
                                     " VM %(instance)s: %(reason)s"),
                            {"instance": instance.name, "reason": exc})
