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
Utility class for path related operations.
"""

import functools
import os
import shutil

from oslo_config import cfg
from oslo_log import log as logging

from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exc
from nova.virt.virtualbox import manage

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CONF.import_opt('instances_path', 'nova.compute.manager')


def create_path(path):
    if os.path.exists(path):
        return
    LOG.debug('Creating directory: %s', path)
    os.makedirs(path)


def delete_path(path):
    """Safely remove path."""
    if not os.path.exists(path):
        return

    if os.path.isdir(path):
        LOG.debug('Remove directory: %s', path)
        shutil.rmtree(path)
    else:
        LOG.debug('Remove file: %s', path)
        os.remove(path)


def _action(function):
    @functools.wraps(function)
    def inner(*args, **kwargs):
        action = kwargs.pop('action', None)
        path = function(*args, **kwargs)
        if action == constants.PATH_OVERWRITE:
            delete_path(path)
            create_path(path)
        elif action == constants.PATH_CREATE:
            create_path(path)
        elif action == constants.PATH_DELETE:
            delete_path(path)
        elif action == constants.PATH_EXISTS:
            return os.path.exists(path)
        return path

    return inner


@_action
def instance_dir(action=None):
    """Return base path for instances."""
    return os.path.normpath(CONF.instances_path)


@_action
def instance_basepath(instance, action=None):
    """Return basepath for received instance.

    :param instance: nova.objects.instance.Instance
    """
    return os.path.join(instance_dir(), instance.name)


@_action
def ephemeral_vhd_path(instance, disk_format, action=None):
    """Return the path for ephemeral vhd.

    :param instance: nova.objects.instance.Instance
    :disk_format:     one disk format from ALL_DISK_FORMAT container
    """
    return os.path.join(instance_basepath(instance),
                        'ephemeral.' + disk_format.lower())


@_action
def base_disk_dir(action=None):
    """Return path for base VHD directory."""
    return os.path.join(CONF.instances_path, '_base')


def base_disk_path(instance):
    return os.path.join(base_disk_dir(action=constants.PATH_CREATE),
                        instance.image_ref)


@_action
def export_dir(instance, action=None):
    """Return the export path for received instance."""
    return os.path.join(instance_basepath(instance), '_export')


@_action
def revert_dir(instance, action=None):
    """Return the export path for received instance."""
    return ("%(instance_basepath)s%(suffix)s" %
            {"instance_basepath": instance_basepath(instance),
             "suffix": '_revert'})


@_action
def root_disk_path(instance, disk_format, action=None):
    """Return the path for the root virtual disk.

    :param instance:  nova.objects.instance.Instance
    :disk_format:     one disk format from ALL_DISK_FORMAT container
    """
    return os.path.join(instance_basepath(instance),
                        'root.' + disk_format.lower())


def get_root_disk_path(instance):
    """Return the path of root virtual disk for received instance."""
    try:
        instance_info = manage.VBoxManage.show_vm_info(instance)
    except vbox_exc.VBoxManageError:
        return None
    root_vhd_path = instance_info.get(constants.DEFAULT_ROOT_ATTACH_POINT)
    return root_vhd_path


def lookup_root_vhd_path(instance):
    for disk_format in constants.ALL_DISK_FORMATS:
        disk = root_disk_path(instance, disk_format)
        if os.path.exists(disk):
            return disk
    return None


def lookup_ephemeral_vhd_path(instance):
    for disk_format in constants.ALL_DISK_FORMATS:
        disk = ephemeral_vhd_path(instance, disk_format)
        if os.path.exists(disk):
            return disk
    return None
