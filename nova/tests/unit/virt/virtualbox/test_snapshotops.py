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

from nova.compute import task_states
from nova import test
from nova.tests.unit import fake_instance
from nova.tests.unit.virt.virtualbox import fake
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exc
from nova.virt.virtualbox import snapshotops


class SnapshotOperationsTestCase(test.NoDBTestCase):

    def setUp(self):
        super(SnapshotOperationsTestCase, self).setUp()
        instance_values = {
            'name': 'fake_name',
            'uuid': 'fake_uuid',
        }

        self._context = 'fake-context'
        self._instance = fake_instance.fake_instance_obj(self._context,
                                                         **instance_values)
        self._snapshotops = snapshotops.SnapshotOperations()

    @mock.patch('os.path.exists')
    @mock.patch('nova.virt.virtualbox.pathutils.delete_path')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.close_medium')
    def test_clenup_disk(self, mock_close_medium, mock_detele_path,
                         mock_path_exists):
        mock_path_exists.return_value = True
        self._snapshotops._clenup_disk(mock.sentinel.disk)

        mock_close_medium.assert_called_once_with(constants.MEDIUM_DISK,
                                                  mock.sentinel.disk)
        mock_detele_path.assert_called_once_with(mock.sentinel.disk)

    @mock.patch('nova.virt.virtualbox.vhdutils.get_image_type')
    @mock.patch('nova.image.glance.get_remote_image_service')
    def test_save_glance_image(self, mock_get_remote_image_service,
                               mock_image_type):
        mock_image_type.return_value = constants.DISK_FORMAT_VDI
        glance_image_service = mock.MagicMock()
        mock_get_remote_image_service.return_value = (glance_image_service,
                                                      mock.sentinel.image_id)
        with mock.patch('nova.virt.virtualbox.snapshotops.open',
                        mock.mock_open(), create=True) as mock_open:
            self._snapshotops._save_glance_image(
                context=self._context, image_id=mock.sentinel.image_id,
                image_vhd_path=mock.sentinel.path)
            mock_open.assert_called_with(mock.sentinel.path, 'rb')
            glance_image_service.update.assert_called_once_with(
                self._context, mock.sentinel.image_id,
                fake.FakeInput.image_metadata(), mock_open())

        mock_get_remote_image_service.assert_called_once_with(
            self._context, mock.sentinel.image_id)

    @mock.patch('os.path')
    @mock.patch('nova.virt.virtualbox.pathutils.export_dir')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.clone_hd')
    @mock.patch('nova.virt.virtualbox.vhdutils.disk_info')
    @mock.patch('nova.virt.virtualbox.pathutils.get_root_disk_path')
    def test_export_path(self, mock_root_disk, mock_disk_info, mock_clone_hd,
                         mock_export_dir, mock_os_path):
        mock_root_disk.return_value = mock.sentinel.current_disk
        mock_export_dir.return_value = mock.sentinel.export_dir
        mock_disk_info.side_effect = [
            # Information regarding the current disk
            {constants.VHD_PARENT_UUID: mock.sentinel.parent_uuid},
            {
                # Information regarding the root disk
                constants.VHD_PATH: mock.sentinel.disk_path,
                constants.VHD_PARENT_UUID: mock.sentinel.parent_uuid,
                constants.VHD_IMAGE_TYPE: mock.sentinel.image_type,
            },
            # Information regarding the parrent disk of root disk
            {constants.VHD_PATH: mock.sentinel.base_path}
        ]

        self._snapshotops._export_disk(self._instance)

        mock_root_disk.assert_called_once_with(self._instance)
        self.assertEqual(2, mock_clone_hd.call_count)

    @mock.patch('os.path')
    @mock.patch('nova.virt.virtualbox.pathutils.export_dir')
    @mock.patch('nova.virt.virtualbox.snapshotops.SnapshotOperations'
                '._clenup_disk')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.clone_hd')
    @mock.patch('nova.virt.virtualbox.vhdutils.disk_info')
    @mock.patch('nova.virt.virtualbox.pathutils.get_root_disk_path')
    def test_export_path_fail(self, mock_root_disk, mock_disk_info,
                              mock_clone_hd, mock_clenup_disk,
                              mock_export_dir, mock_os_path):
        mock_root_disk.return_value = mock.sentinel.current_disk
        mock_disk_info.side_effect = [
            # Information regarding the current disk
            {constants.VHD_PARENT_UUID: mock.sentinel.parent_uuid},
            {
                # Information regarding the root disk
                constants.VHD_PATH: mock.sentinel.disk_path,
                constants.VHD_PARENT_UUID: mock.sentinel.parent_uuid,
                constants.VHD_IMAGE_TYPE: mock.sentinel.image_type,
            },
            # Information regarding the parrent disk of root disk
            {constants.VHD_PATH: mock.sentinel.base_path}
        ] * 2

        mock_clone_hd.side_effect = [
            vbox_exc.VBoxException("fake_error"),
            None, vbox_exc.VBoxException("fake_error"),
        ]

        for _ in range(2):
            # 1. Failed to clone the base disk
            # 2. Failed to clone the root disk
            self.assertRaises(vbox_exc.VBoxException,
                              self._snapshotops._export_disk,
                              self._instance)
        self.assertEqual(2, mock_clenup_disk.call_count)

    @mock.patch('nova.virt.virtualbox.pathutils.get_root_disk_path')
    def test_export_path_no_disk(self, mock_root_disk):
        mock_root_disk.return_value = None
        self.assertRaises(vbox_exc.VBoxException,
                          self._snapshotops._export_disk,
                          self._instance)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.take_snapshot')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.delete_snapshot')
    @mock.patch('nova.virt.virtualbox.snapshotops.SnapshotOperations.'
                '_save_glance_image')
    @mock.patch('nova.virt.virtualbox.snapshotops.SnapshotOperations.'
                '_export_disk')
    def test_take_snapshot(self, mock_export_disk, mock_save_glance_image,
                           mock_delete_snapshot, mock_take_snapshot):
        mock_update = mock.MagicMock()
        mock_export_disk.return_value = mock.sentinel.export_path
        mock_delete_snapshot.side_effect = [
            vbox_exc.VBoxManageError(method="delete_snapshot", reason="n/a")
        ]

        self._snapshotops.take_snapshot(context=self._context,
                                        instance=self._instance,
                                        image_id=mock.sentinel.image_id,
                                        update_task_state=mock_update)

        self.assertEqual(1, mock_take_snapshot.call_count)
        mock_export_disk.assert_called_once_with(self._instance)
        mock_update.has_calls(
            mock.call(task_state=task_states.IMAGE_PENDING_UPLOAD),
            mock.call(task_state=task_states.IMAGE_UPLOADING,
                      expected_state=task_states.IMAGE_PENDING_UPLOAD)
        )
        self.assertEqual(1, mock_delete_snapshot.call_count)
