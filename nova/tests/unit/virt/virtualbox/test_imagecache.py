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

import mock

from nova import test
from nova.tests.unit import fake_instance
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exc
from nova.virt.virtualbox import imagecache


class ImageCacheTestCase(test.NoDBTestCase):
    """Unit tests for the VBoxManage class."""

    _FAKE_BASE_PATH = 'fake-path'
    _FAKE_IMAGE_PATH = 'fake-image-path'

    def setUp(self):
        super(ImageCacheTestCase, self).setUp()
        instance_values = {
            'name': 'fake_name',
            'uuid': 'fake_uuid',
            'image_ref': 'fake_image_ref',
            'user_id': 'fake_user_id',
            'project_id': 'fake_project_id',
        }

        self._context = 'fake-context'
        self._instance = fake_instance.fake_instance_obj(self._context,
                                                         **instance_values)

    @mock.patch('nova.virt.virtualbox.vhdutils.check_disk_uuid')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.close_medium')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.clone_hd')
    @mock.patch('nova.virt.virtualbox.vhdutils.disk_info')
    @mock.patch('nova.virt.images.fetch')
    def test_fetch_image(self, mock_fetch, mock_disk_info, mock_clone_hd,
                         mock_close_medium, mock_check_uuid):
        mock_disk_info.return_value = {
            constants.VHD_IMAGE_TYPE: constants.DISK_FORMAT_VDI
        }
        disk_path = (self._FAKE_IMAGE_PATH + '.' +
                     constants.DISK_FORMAT_VDI.lower())

        imagecache._fetch_image(self._context, self._instance,
                                self._FAKE_IMAGE_PATH)

        mock_disk_info.assert_called_once_with(self._FAKE_IMAGE_PATH)
        mock_fetch.assert_called_once_with(
            self._context, self._instance.image_ref, self._FAKE_IMAGE_PATH,
            self._instance.user_id, self._instance.project_id)
        mock_clone_hd.assert_called_once_with(
            self._FAKE_IMAGE_PATH, disk_path,
            disk_format=constants.DISK_FORMAT_VDI)
        mock_close_medium.assert_called_once_with(
            constants.MEDIUM_DISK, self._FAKE_IMAGE_PATH, delete=True)
        mock_check_uuid.assert_called_once_with(self._FAKE_IMAGE_PATH)

    @mock.patch('os.path.exists')
    @mock.patch('nova.virt.virtualbox.vhdutils.check_disk_uuid')
    @mock.patch('nova.virt.virtualbox.pathutils.delete_path')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.close_medium')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.clone_hd')
    @mock.patch('nova.virt.virtualbox.vhdutils.disk_info')
    @mock.patch('nova.virt.images.fetch')
    def test_fetch_image_fail(self, mock_fetch, mock_disk_info, mock_clone_hd,
                              mock_close_medium, mock_delete_path,
                              mock_check_uuid, mock_exists):
        mock_exists.return_value = True
        mock_disk_info.return_value = {
            constants.VHD_IMAGE_TYPE: constants.DISK_FORMAT_VDI
        }
        mock_clone_hd.side_effect = [vbox_exc.VBoxException("err")]

        self.assertRaises(vbox_exc.VBoxException, imagecache._fetch_image,
                          self._context, self._instance,
                          self._FAKE_IMAGE_PATH)
        self.assertEqual(2, mock_delete_path.call_count)
        mock_check_uuid.assert_called_once_with(self._FAKE_IMAGE_PATH)

    @mock.patch('os.path.exists')
    @mock.patch('os.path.join')
    @mock.patch('nova.utils.synchronized')
    @mock.patch('nova.virt.virtualbox.pathutils.create_path')
    def test_get_cached_image(self, mock_create_path, mock_synchronized,
                              mock_join, mock_exists):
        mock_join.return_value = self._FAKE_BASE_PATH
        mock_exists.side_effect = ([False] * len(constants.ALL_DISK_FORMATS) +
                                   [True])
        imagecache.get_cached_image(self._context, self._instance)
        mock_synchronized.assert_called_once_with(self._FAKE_BASE_PATH)
        mock_synchronized().assert_called_once_with(imagecache._fetch_image)
        mock_synchronized.reset_mock()

        imagecache.get_cached_image(self._context, self._instance)
        self.assertEqual(0, mock_synchronized.call_count)
        self.assertEqual(2, mock_create_path.call_count)
