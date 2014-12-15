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
from nova.virt.virtualbox import exception
from nova.virt.virtualbox import pathutils


class PathUtilsTestCase(test.NoDBTestCase):

    def setUp(self):
        super(PathUtilsTestCase, self).setUp()
        instance_values = {
            'name': 'fake_name',
            'uuid': 'fake_uuid',
        }

        self._context = 'fake-context'
        self._instance = fake_instance.fake_instance_obj(self._context,
                                                         **instance_values)

    @mock.patch('os.makedirs')
    @mock.patch('os.path.exists')
    def test_create_path(self, mock_exists, mock_makedirs):
        mock_exists.side_effect = [False, True]
        for _ in range(2):
            pathutils.create_path(mock.sentinel.path)

        self.assertEqual(2, mock_exists.call_count)
        mock_makedirs.assert_called_once_with(mock.sentinel.path)

    @mock.patch('shutil.rmtree')
    @mock.patch('os.remove')
    @mock.patch('os.path.isdir')
    @mock.patch('os.path.exists')
    def test_delete(self, mock_exists, mock_is_dir, mock_remove, mock_rmtree):
        mock_exists.side_effect = [False, True, True]
        mock_is_dir.side_effect = [True, False]
        for _ in range(3):
            pathutils.delete_path(mock.sentinel.path)

        self.assertEqual(3, mock_exists.call_count)
        self.assertEqual(2, mock_is_dir.call_count)
        mock_remove.assert_called_once_with(mock.sentinel.path)
        mock_rmtree.assert_called_once_with(mock.sentinel.path)

    @mock.patch('os.path.exists')
    @mock.patch('nova.virt.virtualbox.pathutils.delete_path')
    @mock.patch('nova.virt.virtualbox.pathutils.create_path')
    def test_action(self, mock_create, mock_delete, mock_exists):
        path = pathutils.instance_dir()
        pathutils.instance_dir(action=mock.sentinel.invalid_action)
        self.assertEqual(0, mock_create.call_count)
        self.assertEqual(0, mock_delete.call_count)
        self.assertEqual(0, mock_exists.call_count)

        pathutils.instance_dir(action=constants.PATH_CREATE)
        mock_create.assert_called_once_with(path)
        mock_create.reset_mock()

        pathutils.instance_dir(action=constants.PATH_DELETE)
        mock_delete.assert_called_once_with(path)
        mock_delete.reset_mock()

        pathutils.instance_dir(action=constants.PATH_EXISTS)
        mock_exists.assert_called_once_with(path)
        mock_exists.reset_mock()

        pathutils.instance_dir(action=constants.PATH_OVERWRITE)
        mock_delete.assert_called_once_with(path)
        mock_create.assert_called_once_with(path)

    @mock.patch('os.path.normpath')
    def test_instance_dir(self, mock_join):
        pathutils.instance_dir()
        self.assertEqual(1, mock_join.call_count)

    @mock.patch('os.path.join')
    @mock.patch('nova.virt.virtualbox.pathutils.instance_dir')
    def test_instance_basepath(self, mock_instance_dir, mock_join):
        pathutils.instance_basepath(self._instance)

        mock_join.assert_called_once_with(mock_instance_dir(),
                                          self._instance.name)

    @mock.patch('os.path.join')
    @mock.patch('nova.virt.virtualbox.pathutils.instance_basepath')
    def test_ephemeral_vhd_path(self, mock_instance_basepath, mock_join):
        pathutils.ephemeral_vhd_path(self._instance, 'fake-disk-format')

        mock_instance_basepath.assert_called_once_with(self._instance)
        self.assertEqual(1, mock_join.call_count)

    @mock.patch('os.path.join')
    def test_base_disk_dir(self, mock_join):
        pathutils.base_disk_dir()

        self.assertEqual(1, mock_join.call_count)

    @mock.patch('os.path.join')
    @mock.patch('nova.virt.virtualbox.pathutils.base_disk_dir')
    def test_base_disk_path(self, mock_base_disk, mock_join):
        pathutils.base_disk_path(self._instance)

        self.assertEqual(1, mock_base_disk.call_count)
        self.assertEqual(1, mock_join.call_count)

    @mock.patch('os.path.join')
    @mock.patch('nova.virt.virtualbox.pathutils.instance_basepath')
    def test_root_disk_path(self, mock_instance_basepath, mock_join):
        pathutils.root_disk_path(self._instance, 'fake-disk-format')

        mock_instance_basepath.assert_called_once_with(self._instance)
        self.assertEqual(1, mock_join.call_count)

    @mock.patch('os.path.join')
    @mock.patch('nova.virt.virtualbox.pathutils.instance_basepath')
    def test_export_dir(self, mock_instance_basepath, mock_join):
        pathutils.export_dir(self._instance)

        mock_instance_basepath.assert_called_once_with(self._instance)
        self.assertEqual(1, mock_join.call_count)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.show_vm_info')
    def test_get_root_disk_path(self, mock_vm_info):
        mock_vm_info.return_value = {
            constants.DEFAULT_ROOT_ATTACH_POINT: mock.sentinel.path}

        self.assertEqual(mock.sentinel.path,
                         pathutils.get_root_disk_path(self._instance))

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.show_vm_info')
    def test_get_root_disk_path_fail(self, mock_vm_info):
        mock_vm_info.side_effect = [
            exception.VBoxManageError("err"),
            {}
        ]
        for _ in range(2):
            self.assertIsNone(pathutils.get_root_disk_path(self._instance))
