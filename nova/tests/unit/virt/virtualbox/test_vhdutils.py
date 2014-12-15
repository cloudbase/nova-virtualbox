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
from oslo_utils import units

from nova import exception as nova_exception
from nova import test
from nova.tests.unit import fake_instance
from nova.tests.unit.virt.virtualbox import fake
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exception
from nova.virt.virtualbox import vhdutils


class VHDUtilsTestCase(test.NoDBTestCase):

    def setUp(self):
        super(VHDUtilsTestCase, self).setUp()
        instance_values = {
            'name': 'fake_name',
            'uuid': 'fake_uuid',
            'image_ref': 'fake_image_ref'
        }

        self._context = 'fake-context'
        self._instance = fake_instance.fake_instance_obj(self._context,
                                                         **instance_values)

    def test_process_vhd_field(self):
        output = {}
        input_line = (
            'State:          created     ',
            'Storage format: VDI         ',
            'Capacity:       1024 MBytes ',
            'Parent UUID:    base        ',
        )
        for line in input_line:
            self.assertTrue(vhdutils._process_vhd_field(line, output))

        self.assertEqual('created', output[constants.VHD_STATE])
        self.assertEqual(constants.DISK_FORMAT_VDI,
                         output[constants.VHD_IMAGE_TYPE])
        self.assertEqual(units.Gi, output[constants.VHD_CAPACITY])
        self.assertIsNone(output[constants.VHD_PARENT_UUID])

    def test_process_vhd_field_fail(self):
        output = {}
        input_line = ('field=value', 'field    value', 'key:value')
        for line in input_line:
            self.assertFalse(vhdutils._process_vhd_field(line, output))
        self.assertEqual({}, output)

    def test_predict_size(self):
        size_map = {
            '1M': units.Mi, '1 mega': units.Mi,
            '1Mi': units.Mi, '1 mebi': units.Mi,
            '1 byte': 1, '1 k': units.Ki,
        }
        for size, expected_response in size_map.items():
            self.assertEqual(expected_response, vhdutils.predict_size(size))

    def test_predict_size_fail(self):
        self.assertRaises(ValueError, vhdutils.predict_size, "10 Ni")

    def test_get_controller_disks(self):
        instance_info = {
            '"SATA-0-0"': mock.sentinel.path,
            'SATA-1-0': mock.sentinel.path,
            'SATA-ImageUUID-1-0': mock.sentinel.uuid
        }
        expected_dict = {
            (0, 0): {"path": mock.sentinel.path,
                     "uuid": None},
            (1, 0): {"path": mock.sentinel.path,
                     "uuid": mock.sentinel.uuid}
        }

        self.assertEqual(expected_dict,
                         vhdutils.get_controller_disks("SATA", instance_info))

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.show_vm_info')
    @mock.patch('nova.virt.virtualbox.vhdutils.get_controller_disks')
    def test_get_controllers(self, mock_controller_disks, mock_vm_info):
        mock_controller_disks.return_value = mock.sentinel.disks
        mock_vm_info.return_value = {
            'storagecontrollername1': fake.FAKE_SYSTEM_BUS_IDE,
            'storagecontrollername2': fake.FAKE_SYSTEM_BUS_SATA,
            'storagecontrollername3': fake.FAKE_SYSTEM_BUS_SCSI,
            'key': None
        }
        controllers = {fake.FAKE_SYSTEM_BUS_IDE: mock.sentinel.disks,
                       fake.FAKE_SYSTEM_BUS_SATA: mock.sentinel.disks,
                       fake.FAKE_SYSTEM_BUS_SCSI: mock.sentinel.disks}
        response = vhdutils.get_controllers(self._instance)

        mock_vm_info.assert_called_once_with(self._instance)
        self.assertEqual(len(controllers), mock_controller_disks.call_count)
        self.assertEqual(controllers, response)

    @mock.patch('nova.virt.virtualbox.vhdutils.get_controllers')
    def test_get_available_attach_point(self, mock_get_controllers):
        mock_get_controllers.return_value = {
            mock.sentinel.controller: {
                (0, 0): {"path": mock.sentinel.path,
                         "uuid": mock.sentinel.uuid},
                (1, 0): {"path": None,
                         "uuid": None},
            }
        }

        attach_point = vhdutils.get_available_attach_point(
            self._instance, mock.sentinel.controller)

        self.assertEqual((1, 0), attach_point)

    @mock.patch('nova.virt.virtualbox.vhdutils.get_controllers')
    def test_get_available_attach_point_fail(self, mock_get_controllers):
        mock_get_controllers.return_value = {
            mock.sentinel.controller: {
                (0, 0): {"path": mock.sentinel.path,
                         "uuid": mock.sentinel.uuid},
                (1, 0): {"path": mock.sentinel.path,
                         "uuid": mock.sentinel.uuid}
            }
        }

        self.assertRaises(vbox_exception.VBoxException,
                          vhdutils.get_available_attach_point,
                          self._instance, mock.sentinel.invalid)
        self.assertRaises(vbox_exception.VBoxException,
                          vhdutils.get_available_attach_point,
                          self._instance, mock.sentinel.controller)

    @mock.patch('nova.virt.virtualbox.vhdutils.get_controller_disks')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.show_vm_info')
    def test_get_attach_point(self, mock_vm_info, mock_controller_disks):
        mock_vm_info.return_value = mock.sentinel.instance_info
        mock_controller_disks.return_value = {
            (0, 0): {"path": mock.sentinel.path,
                     "uuid": mock.sentinel.uuid}
        }

        self.assertEqual((0, 0), vhdutils.get_attach_point(
            self._instance, "SATA", mock.sentinel.uuid))
        self.assertIsNone(vhdutils.get_attach_point(
            self._instance, "SATA", mock.sentinel.alt_uuid))

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.list')
    def test_get_hard_disks(self, mock_list_hdds):
        mock_list_hdds.return_value = (
            'UUID:           uuid_disk_1\n\n'
            'UUID:           uuid_disk_2\n\n'
        )
        response = vhdutils.get_hard_disks()

        self.assertEqual({"uuid_disk_1": {}, "uuid_disk_2": {}},
                         response)

    @mock.patch('nova.virt.virtualbox.vhdutils.disk_info')
    def test_get_image_type(self, mock_disk_info):
        disk_path = mock.sentinel.disk_path
        mock_disk_info.return_value = {
            constants.VHD_IMAGE_TYPE: constants.DISK_FORMAT_VHD}

        self.assertEqual(constants.DISK_FORMAT_VHD,
                         vhdutils.get_image_type(disk_path))

    @mock.patch('nova.virt.virtualbox.vhdutils.disk_info')
    def test_get_image_type_fail(self, mock_disk_info):
        disk_path = mock.sentinel.disk_path
        mock_disk_info.side_effect = [
            vbox_exception.VBoxManageError(method="showhdinfo",
                                           reason="fake-error"),
            {constants.VHD_IMAGE_TYPE: 'fake-image-type'},
        ]

        self.assertIsNone(vhdutils.get_image_type(disk_path))
        self.assertRaises(nova_exception.InvalidDiskFormat,
                          vhdutils.get_image_type, disk_path)

    def test_disk_info(self):
        # TODO(alexandrucoman): Add test for vhdutils.disk_info
        pass

    def test_is_resize_required(self):
        self.assertFalse(vhdutils.is_resize_required(
            mock.sentinel.disk, 1024, 1024, self._instance))

        self.assertTrue(vhdutils.is_resize_required(
            mock.sentinel.disk, 1024, 2048, self._instance))

        self.assertRaises(nova_exception.CannotResizeDisk,
                          vhdutils.is_resize_required,
                          mock.sentinel.disk, 2048, 1024, self._instance)

    def test_check_disk_uuid(self):
        # TODO(alexandrucoman): Add test for vhdutils.check_hdds
        pass
