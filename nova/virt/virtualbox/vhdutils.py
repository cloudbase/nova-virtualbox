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
Helper methods for operations related to the management of virtual
hard disks and their settings.
"""

import re

from oslo_log import log as logging

from nova import exception
from nova.i18n import _LE
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exc
from nova.virt.virtualbox import manage


SYMBOLS = {
    'customary_symbols': ('B', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y'),
    'customary_names': ('byte', 'kilo', 'mega', 'giga', 'tera',
                        'peta', 'exa', 'zetta', 'iotta'),
    # Note(alexandrucoman): More information can be found on the following link
    #                       http://goo.gl/uyQruU
    'IEC_symbols': ('Bi', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi', 'Yi'),
    'IEC_names': ('byte', 'kibi', 'mebi', 'gibi', 'tebi', 'pebi',
                  'exbi', 'zebi', 'yobi'),
}
LOG = logging.getLogger(__name__)


def _process_vhd_field(line, current_vhd):
    key, separator, value = line.partition(':')
    if separator != ':':
        return False

    hd_info_key = constants.SHOW_HD_INFO_KEYS.get(key.strip(), None)
    if not hd_info_key:
        LOG.debug("Unexpected key `%(key)s` for vhd.", {"key": key})
        return False

    value = value.strip()
    if hd_info_key in (constants.VHD_SIZE_ON_DISK, constants.VHD_CAPACITY):
        current_vhd[hd_info_key] = predict_size(value.replace('Bytes', ''))
    elif hd_info_key == constants.VHD_PARENT_UUID:
        current_vhd[hd_info_key] = value if value != "base" else None
    else:
        current_vhd[hd_info_key] = value
    return True


def predict_size(size):
    """Attempts to guess the string format based on default symbols
    set and return the corresponding bytes as an integer.
    """
    initial_size = size.strip()
    numerical = ""
    while (initial_size and initial_size[0:1].isdigit() or
            initial_size[0:1] == '.'):
        numerical += initial_size[0]
        initial_size = initial_size[1:]
    numerical = float(numerical)

    letter = initial_size.strip()
    for set_name, symbol_set in SYMBOLS.items():
        if letter in symbol_set:
            break
    else:
        if letter == 'k':
            # Treat `k` as an alias for `K`
            symbol_set = SYMBOLS['customary_symbols']
            letter = letter.upper()
        else:
            raise ValueError("Can't interpret %(size)s" %
                             {"size": size})

    if letter == symbol_set[0]:
        symbol_value = 1
    else:
        symbol_value = 1 << symbol_set.index(letter) * 10

    return int(numerical * symbol_value)


def get_controller_disks(controller_name, instance_info):
    """Get all the available information regarding disks attached to
    the received strorage controller.
    """
    disks = {}
    regexp = re.compile(r'%s(?P<uuid>-ImageUUID)*-(?P<port>\d+)-'
                        '(?P<device>\d+)' % controller_name)
    for key, value in instance_info.items():
        info = regexp.search(key)
        if not info:
            continue

        port = int(info.group("port"))
        device = int(info.group("device"))
        device_map = disks.setdefault((port, device),
                                      {"path": None, "uuid": None})
        device_map["uuid" if info.group("uuid") else "path"] = value

    return disks


def get_controllers(instance):
    """Get all the available information regarding Storage Controllers
    from show_vm_info for the received instance.
    """
    instance_info = manage.VBoxManage.show_vm_info(instance)
    controllers = {}

    for key in instance_info:
        if key.startswith('storagecontrollername'):
            controller_name = instance_info[key]
            controllers[controller_name] = get_controller_disks(
                controller_name, instance_info)
    return controllers


def get_available_attach_point(instance, controller_name):
    storage_info = get_controllers(instance)
    controller = storage_info.get(controller_name)
    if not controller:
        details = _LE("Controller %(controller)s do not exists!")
        raise vbox_exc.VBoxException(details % {"controller": controller_name})

    for attach_point, disk in controller.items():
        if not disk["uuid"]:
            return attach_point

    raise vbox_exc.VBoxException(_LE("Exceeded the maximum number of slots"))


def get_attach_point(instance, controller_name, disk_uuid):
    instance_info = manage.VBoxManage.show_vm_info(instance)
    controller = get_controller_disks(controller_name, instance_info)
    for attach_point in controller:
        if disk_uuid == controller[attach_point]["uuid"]:
            return attach_point
    return None


def get_hard_disks():
    """Return information about virtual disk images currently in use by
    hypervisor, including all their settings, the unique identifiers (UUIDs)
    associated with them by VirtualBox and all files associated with them.
    """
    output = manage.VBoxManage.list(constants.HDDS_INFO)
    current_vhd = {}
    hdds_map = {}
    for line in output.splitlines():
        if not line:
            hdd_uuid = current_vhd.pop(constants.VHD_UUID, None)
            if hdd_uuid:
                hdds_map[hdd_uuid] = current_vhd
            current_vhd = {}
            continue
        _process_vhd_field(line, current_vhd)
    return hdds_map


def get_image_type(disk_path):
    """Get image disk type from the virtual hard disk information."""
    try:
        information = disk_info(disk_path)
    except vbox_exc.VBoxManageError:
        # TODO(alexandrucoman): Process information from exception and
        #                       find another way to get disk type
        return None

    disk_format = information.get(constants.VHD_IMAGE_TYPE, None)
    if disk_format not in constants.ALL_DISK_FORMATS:
        raise exception.InvalidDiskFormat(disk_format=disk_format)

    return disk_format


def disk_info(hard_disk):
    """Return a dictionary with information regarding a virtul hard disk.

    The dictionary with information regarding hard disk image
    contains:
        :VHD_UUID:
        :VHD_PARENT_UUID:
        :VHD_STATE:
        :VHD_TYPE:
        :VHD_PATH:           the path for virtual hard drive
        :VHD_IMAGE_TYPE:     value from ALL_DISK_FORMATS
        :VHD_VARIANT:        value from ALL_VARIANTS
        :VHD_CAPACITY:       (int) virtual disk capacity
        :VHD_SIZE_ON_DISK:   (int) size on disk for virtual disk
        :VHD_USED_BY:        (list)
    """
    current_vhd = {}
    child_uuids = []
    output = manage.VBoxManage.show_hd_info(hard_disk)
    for line in output.splitlines():
        if not _process_vhd_field(line, current_vhd):
            child_uuids.append(line.strip())

    if constants.VHD_CHILD_UUIDS in current_vhd:
        child_uuids.append(current_vhd[constants.VHD_CHILD_UUIDS])

    current_vhd[constants.VHD_CHILD_UUIDS] = child_uuids

    return current_vhd


def check_disk_uuid(disk_file):
    try:
        disk_info = manage.VBoxManage.show_hd_info(disk_file)
        LOG.debug("The disk appears to be available: %(disk_info)s",
                  {"disk_info": disk_info})
        return
    except vbox_exc.VBoxInvalid as error:
        LOG.debug("The disk cannot be registered because: %(reason)s",
                  {"reason": error})

    LOG.debug('Assign a new UUID to `%(disk)s`', {"disk": disk_file})
    manage.VBoxManage.set_vhd_uuid(disk_file)


def is_resize_required(disk_path, old_size, new_size, instance):
    """Check if resize is required for received disk."""
    if new_size < old_size:
        error_msg = _LE(
            "Cannot resize a disk to a smaller size, the original "
            "size is %(old_size)s, the newer size is %(new_size)s"
        ) % {'old_size': old_size, 'new_size': new_size}

        raise exception.CannotResizeDisk(error_msg)

    elif new_size > old_size:
        LOG.debug("Resizing disk %(disk_path)s to new size %(new_size)s" %
                  {'new_size': new_size, 'disk_path': disk_path},
                  instance=instance)
        return True

    return False
