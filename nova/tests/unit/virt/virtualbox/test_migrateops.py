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
from nova.virt.virtualbox import migrationops


class MigrationOperationsTestCase(test.NoDBTestCase):

    def setUp(self):
        super(MigrationOperationsTestCase, self).setUp()
        instance_values = {
            'name': 'fake_name',
            'uuid': 'fake_uuid',
        }

        self._context = 'fake-context'
        self._instance = fake_instance.fake_instance_obj(self._context,
                                                         **instance_values)
        self._migrationops = migrationops.MigrationOperations()

    @mock.patch('os.path.join')
    @mock.patch('os.listdir')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.close_medium')
    def test_remove_disks(self, mock_close_medium, mock_listdir, mock_join):
        mock_listdir.return_value = [mock.sentinel.disk1, mock.sentinel.disk2]
        mock_join.side_effect = [mock.sentinel.disk1, mock.sentinel.disk2]
        self._migrationops._remove_disks(mock.sentinel.path)

        mock_listdir.assert_called_once_with(mock.sentinel.path)
        mock_join.assert_has_calls([
            mock.call(mock.sentinel.path, mock.sentinel.disk1),
            mock.call(mock.sentinel.path, mock.sentinel.disk2),
        ])
        mock_close_medium.assert_has_calls([
            mock.call(constants.MEDIUM_DISK, mock.sentinel.disk1,
                      delete=True),
            mock.call(constants.MEDIUM_DISK, mock.sentinel.disk2,
                      delete=True)
        ])

    @mock.patch('os.path.join')
    @mock.patch('os.listdir')
    @mock.patch('nova.virt.virtualbox.pathutils.delete_path')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.close_medium')
    def test_remove_disks_close_fail(self, mock_close_medium, mock_delete,
                                     mock_listdir, mock_join):
        mock_listdir.return_value = [mock.sentinel.disk]
        mock_join.return_value = mock.sentinel.disk
        mock_close_medium.side_effect = [vbox_exc.VBoxException('error')]
        self._migrationops._remove_disks(mock.sentinel.path)

        mock_delete.assert_called_once_with(mock.sentinel.disk)

    @mock.patch('nova.virt.virtualbox.vhdutils.disk_info')
    @mock.patch('nova.virt.virtualbox.vhdutils.check_disk_uuid')
    def test_check_disk(self, mock_check_uuid, mock_disk_info):
        mock_disk_info.return_value = {constants.VHD_PARENT_UUID: None}
        self._migrationops._check_disk(mock.sentinel.disk_file,
                                       mock.sentinel.base_disk)

        mock_check_uuid.assert_called_once_with(mock.sentinel.disk_file)
        mock_disk_info.assert_called_once_with(mock.sentinel.disk_file)

    @mock.patch('nova.virt.virtualbox.vhdutils.get_hard_disks')
    @mock.patch('nova.virt.virtualbox.vhdutils.disk_info')
    @mock.patch('nova.virt.virtualbox.vhdutils.check_disk_uuid')
    def test_check_disk_cow(self, mock_check_uuid, mock_disk_info,
                            mock_get_hard_disks):
        mock_disk_info.return_value = {
            constants.VHD_PARENT_UUID: mock.sentinel.parent_uuid
        }
        mock_get_hard_disks.return_value = [mock.sentinel.parent_uuid]
        self._migrationops._check_disk(mock.sentinel.disk_file,
                                       mock.sentinel.base_disk)

        mock_check_uuid.assert_called_once_with(mock.sentinel.disk_file)
        mock_disk_info.assert_called_once_with(mock.sentinel.disk_file)
        mock_get_hard_disks.assert_called_once_with()

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.set_disk_parent_uuid')
    @mock.patch('nova.virt.virtualbox.vhdutils.get_hard_disks')
    @mock.patch('nova.virt.virtualbox.vhdutils.disk_info')
    @mock.patch('nova.virt.virtualbox.vhdutils.check_disk_uuid')
    def test_check_disk_parent_missing(self, mock_check_uuid, mock_disk_info,
                                       mock_get_hard_disks,
                                       mock_set_parrent_uuid):
        mock_get_hard_disks.return_value = []
        mock_disk_info.side_effect = [
            # No information available for disk file
            vbox_exc.VBoxException('error'),
            # Information regarding the base disk
            {constants.VHD_UUID: mock.sentinel.base_disk_uuid}
        ]
        self._migrationops._check_disk(mock.sentinel.disk_file,
                                       mock.sentinel.base_disk)

        mock_check_uuid.assert_called_once_with(mock.sentinel.disk_file)
        mock_disk_info.assert_has_calls([
            mock.call(mock.sentinel.disk_file),
            mock.call(mock.sentinel.base_disk)
        ])
        mock_get_hard_disks.assert_called_once_with()
        mock_set_parrent_uuid.assert_called_once_with(
            mock.sentinel.disk_file, mock.sentinel.base_disk_uuid)
