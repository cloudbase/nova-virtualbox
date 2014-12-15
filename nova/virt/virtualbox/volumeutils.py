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
Helper methods for storage related operations(attach, detach, etc).
"""

import collections

from oslo_log import log as logging

from nova import block_device
from nova.virt import driver
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import vhdutils

LOG = logging.getLogger(__name__)


def group_block_devices_by_type(block_device_mapping):
    """Return devices grouped by driver volume type."""
    block_devices = collections.defaultdict(list)
    for volume in block_device_mapping:
        connection_info = volume['connection_info']
        volume_type = connection_info.get('driver_volume_type')
        block_devices[volume_type].append(volume)
    return block_devices


def volume_in_mapping(mount_device, block_device_info):
    block_device_list = [
        block_device.strip_dev(volume['mount_device']) for volume in
        driver.block_device_info_get_mapping(block_device_info)
    ]

    swap = driver.block_device_info_get_swap(block_device_info)
    if driver.swap_is_usable(swap):
        block_device_list.append(block_device.strip_dev(
            swap['device_name']))
    block_device_list.extend([
        block_device.strip_dev(ephemeral['device_name']) for ephemeral in
        driver.block_device_info_get_ephemerals(block_device_info)])


def ebs_root_in_block_devices(block_device_info):
    if not block_device_info:
        return

    root_device = block_device_info.get('root_device_name')
    if not root_device:
        root_device = constants.DEFAULT_ROOT_DEVICE

    return volume_in_mapping(root_device, block_device_info)


def volume_uuid(connection_info):
    """Returm the volume uuid if is already registered."""
    data = connection_info['data']
    target_lun = str(data['target_lun'])
    target_iqn = data['target_iqn']
    target_portal = data['target_portal'].split(':')[0]

    registered_hdds = vhdutils.get_hard_disks()
    for uuid, disk in registered_hdds.items():
        if '|' not in disk[constants.VHD_PATH]:
            continue

        disk_info = disk[constants.VHD_PATH].split('|')
        for target_info in (target_lun, target_iqn, target_portal):
            if target_info not in disk_info:
                break
        else:
            return uuid

    return None
