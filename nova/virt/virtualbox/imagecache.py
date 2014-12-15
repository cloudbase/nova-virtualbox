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

import os

from oslo_utils import excutils

from nova import exception
from nova import utils
from nova.virt import images
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exc
from nova.virt.virtualbox import manage
from nova.virt.virtualbox import pathutils
from nova.virt.virtualbox import vhdutils


def _fetch_image(context, instance, image_path):
    disk_path = None
    try:
        images.fetch(context, instance.image_ref, image_path,
                     instance.user_id, instance.project_id)
        # Avoid conflicts
        vhdutils.check_disk_uuid(image_path)

        disk_info = vhdutils.disk_info(image_path)
        disk_format = disk_info[constants.VHD_IMAGE_TYPE]
        disk_path = image_path + "." + disk_format.lower()

        manage.VBoxManage.clone_hd(image_path, disk_path,
                                   disk_format=disk_format)
        manage.VBoxManage.close_medium(constants.MEDIUM_DISK, image_path,
                                       delete=True)

    except (vbox_exc.VBoxException, exception.NovaException):
        with excutils.save_and_reraise_exception():
            for path in (image_path, disk_path):
                if path and os.path.exists(path):
                    manage.VBoxManage.close_medium(constants.MEDIUM_DISK,
                                                   path)
                    pathutils.delete_path(path)

    return disk_path


def get_cached_image(context, instance):
    base_disk_path = pathutils.base_disk_path(instance)

    for disk_format in constants.ALL_DISK_FORMATS:
        test_path = base_disk_path + '.' + disk_format.lower()
        if os.path.exists(test_path):
            return test_path

    sync = utils.synchronized(base_disk_path)
    synchronized_fetch_image = sync(_fetch_image)
    disk_path = synchronized_fetch_image(context, instance, base_disk_path)

    return disk_path
