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
from oslo_concurrency import processutils

from nova import exception
from nova import test
from nova.tests.unit import fake_instance
from nova.tests.unit.virt.virtualbox import fake
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exc
from nova.virt.virtualbox import manage


class VBoxManageTestCase(test.NoDBTestCase):
    """Unit tests for the VBoxManage class."""

    _FAKE_STDERR = 'fake-error'
    _RETRY_COUNT = 2

    def setUp(self):
        super(VBoxManageTestCase, self).setUp()
        instance_values = {
            'name': 'fake_name',
            'uuid': 'fake_uuid',
        }

        self.flags(retry_count=self._RETRY_COUNT, group="virtualbox")
        self.flags(retry_interval=0, group="virtualbox")
        self._context = 'fake-context'
        self._instance = fake_instance.fake_instance_obj(self._context,
                                                         **instance_values)
        self._vbox_manage = manage.VBoxManage()

    @mock.patch('nova.utils.execute')
    def test_execute(self, mock_execute):
        stdout = mock.sentinel.stdout
        exc = processutils.ProcessExecutionError(stdout=stdout,
                                                 stderr=self._FAKE_STDERR)
        mock_execute.side_effect = [(stdout, self._FAKE_STDERR), exc]
        for _ in range(2):
            response = manage.VBoxManage._execute('command')
            self.assertEqual((stdout, self._FAKE_STDERR), response)

    @mock.patch('nova.utils.execute')
    def test_execute_retry(self, mock_execute):
        stdout = mock.sentinel.stdout
        mock_execute.side_effect = [
            (stdout, constants.VBOX_E_ACCESSDENIED)] * self._RETRY_COUNT
        self._vbox_manage._execute('command')
        self.assertEqual(self._RETRY_COUNT, mock_execute.call_count)

    def test_check_stderr(self):
        self.assertRaises(exception.InstanceNotFound,
                          self._vbox_manage._check_stderr,
                          constants.VBOX_E_INSTANCE_NOT_FOUND, self._instance)
        self.assertRaises(exception.InstanceInvalidState,
                          self._vbox_manage._check_stderr,
                          constants.VBOX_E_INVALID_VM_STATE, self._instance)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._check_stderr')
    def test_storageattach(self, mock_check_stderr, mock_execute):
        arguments = [self._instance]
        arguments.extend([mock.sentinel.arg] * 5)
        arguments.append(mock.sentinel.extra_arg)
        mock_execute.side_effect = [(None, None), (None, self._FAKE_STDERR)]

        response = self._vbox_manage._storageattach(*arguments)
        self.assertEqual(0, mock_check_stderr.call_count)
        self.assertEqual((None, None), response)

        response = self._vbox_manage._storageattach(*arguments)
        self.assertEqual(1, mock_check_stderr.call_count)
        self.assertEqual((None, self._FAKE_STDERR), response)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_control_vm(self, mock_execute):
        stdout = mock.sentinel.stdout
        mock_execute.side_effect = [(stdout, None), (stdout, None)]
        for state in (constants.STATE_POWER_OFF, constants.ACPI_POWER_BUTTON):
            self.assertIsNone(self._vbox_manage.control_vm(self._instance,
                                                           state))

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._check_stderr')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_control_vm_fail(self, mock_execute, mock_check_stderr):
        mock_execute.side_effect = [(None, self._FAKE_STDERR)]
        state = constants.ALL_STATES[0]

        self.assertRaises(vbox_exc.VBoxValueNotAllowed,
                          self._vbox_manage.control_vm,
                          self._instance, mock.sentinel.state)
        self.assertEqual(0, mock_check_stderr.call_count)

        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.control_vm,
                          self._instance, state)
        mock_check_stderr.assert_called_once_with(
            self._FAKE_STDERR, self._instance, self._vbox_manage.CONTROL_VM)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._check_stderr')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_start_vm(self, mock_execute, mock_check_stderr):
        stdout = mock.sentinel.stdout
        method = constants.ALL_START_VM[0]
        mock_execute.side_effect = [(stdout, None)]

        self.assertIsNone(self._vbox_manage.start_vm(self._instance, method))
        self.assertEqual(1, mock_execute.call_count)
        self.assertEqual(0, mock_check_stderr.call_count)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._check_stderr')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_start_vm_fail(self, mock_execute, mock_check_stderr):
        mock_execute.side_effect = [(None, self._FAKE_STDERR)]
        method = constants.ALL_START_VM[0]

        self.assertRaises(vbox_exc.VBoxValueNotAllowed,
                          self._vbox_manage.start_vm,
                          self._instance, mock.sentinel.method)
        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.start_vm,
                          self._instance, method)
        mock_check_stderr.assert_called_once_with(
            self._FAKE_STDERR, self._instance, self._vbox_manage.START_VM)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_modify_vm(self, mock_execute):
        stdout = mock.sentinel.stdout
        mock_execute.side_effect = [(stdout, None)]

        self.assertIsNone(self._vbox_manage.modify_vm(
            self._instance, constants.ALL_VM_FIELDS[0], mock.sentinel.value))
        self.assertEqual(1, mock_execute.call_count)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._check_stderr')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_modify_vm_fail(self, mock_execute, mock_check_stderr):
        mock_execute.side_effect = [(None, self._FAKE_STDERR)]

        self.assertRaises(vbox_exc.VBoxValueNotAllowed,
                          self._vbox_manage.modify_vm,
                          self._instance, mock.sentinel.field)

        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.modify_vm,
                          self._instance, constants.ALL_VM_FIELDS[0])
        mock_check_stderr.assert_called_once_with(
            self._FAKE_STDERR, self._instance, self._vbox_manage.MODIFY_VM)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_modify_network(self, mock_execute):
        stdout = mock.sentinel.stdout
        field = constants.ALL_NETWORK_FIELDS[0]
        mock_execute.side_effect = [(stdout, None)]
        method_input = (self._instance, field,
                        mock.sentinel.index, mock.sentinel.value)

        self.assertIsNone(self._vbox_manage.modify_network(*method_input))
        self.assertEqual(1, mock_execute.call_count)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_modify_network_fail(self, mock_execute):
        mock_execute.side_effect = [(None, self._FAKE_STDERR)]
        fake_input = [self._instance, mock.sentinel.field,
                      mock.sentinel.index, mock.sentinel.value]

        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.modify_network,
                          *fake_input)

        fake_input[1] = constants.ALL_VM_FIELDS[0]
        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.modify_network,
                          *fake_input)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_list(self, mock_execute):
        stdout, stderr = mock.sentinel.stdout, mock.sentinel.stderr
        mock_execute.side_effect = [(stdout, stderr), (stdout, None)]
        self.assertRaises(vbox_exc.VBoxManageError, self._vbox_manage.list,
                          mock.sentinel.info)
        self.assertEqual(stdout, self._vbox_manage.list(mock.sentinel.info))

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_show_vm_info(self, mock_execute):
        mock_execute.side_effect = [
            ('"a"="b"', None), ('\n"a"="b"\n', None), ('"a" = "b"', None),
            ('"none"="none"', None)
        ]

        for _ in range(3):
            response = self._vbox_manage.show_vm_info(self._instance)
            self.assertEqual({'a': 'b'}, response)

        response = self._vbox_manage.show_vm_info(self._instance)
        self.assertIsNone(response["none"])

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_show_vm_info_fail(self, mock_execute):
        mock_execute.side_effect = [(None, self._FAKE_STDERR),
                                    ('invalid', None)]

        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.show_vm_info,
                          self._instance)
        self.assertEqual({}, self._vbox_manage.show_vm_info(self._instance))

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_show_hd_info(self, mock_execute):
        mock_execute.return_value = (mock.sentinel.output, None)
        response = self._vbox_manage.show_hd_info(mock.sentinel.vhd)

        mock_execute.assert_called_once_with(self._vbox_manage.SHOW_HD_INFO,
                                             mock.sentinel.vhd)
        self.assertEqual(mock.sentinel.output, response)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_show_hd_info_fail(self, mock_execute):
        mock_execute.return_value = (None, self._FAKE_STDERR)

        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.show_hd_info, mock.sentinel.vhd)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_create_hd(self, mock_execute):
        filename = mock.sentinel.filename
        mock_execute.side_effect = [
            (mock.sentinel.stdout, constants.VBOX_E_FILE_ERROR),
            ('UUID: fake-uuid', None),
            ('fake-output', None)
        ]

        self.assertRaises(exception.DestinationDiskExists,
                          self._vbox_manage.create_hd, filename, 1)
        self.assertEqual('fake-uuid', self._vbox_manage.create_hd(filename, 1))
        self.assertIsNone(self._vbox_manage.create_hd(filename, 1))

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_create_hd_invalid_args(self, mock_execute):
        filename, size = mock.sentinel.filename, mock.sentinel.size
        self.assertRaises(
            exception.InvalidDiskFormat, self._vbox_manage.create_hd,
            filename, size, mock.sentinel.invalid_disk_format)
        self.assertRaises(
            vbox_exc.VBoxValueNotAllowed, self._vbox_manage.create_hd,
            filename, size, constants.DEFAULT_DISK_FORMAT,
            mock.sentinel.invalid_variant)
        self.assertRaises(
            exception.InvalidDiskInfo, self._vbox_manage.create_hd,
            filename, -1, constants.DEFAULT_DISK_FORMAT,
            constants.DEFAULT_VARIANT)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_clone_hd(self, mock_execute):
        mock_execute.side_effect = [(None, None), (None, None), (None, None)]
        calls = [
            mock.call("clonehd", mock.sentinel.path, mock.sentinel.new_path),
            mock.call("clonehd", mock.sentinel.path, mock.sentinel.new_path,
                      "--format", mock.sentinel.format),
            mock.call("clonehd", mock.sentinel.path, mock.sentinel.new_path,
                      "--variant", mock.sentinel.variant)
        ]
        self.assertIsNone(manage.VBoxManage.clone_hd(mock.sentinel.path,
                                                     mock.sentinel.new_path))
        self._vbox_manage.clone_hd(mock.sentinel.path, mock.sentinel.new_path,
                                   disk_format=mock.sentinel.format)
        self._vbox_manage.clone_hd(mock.sentinel.path, mock.sentinel.new_path,
                                   variant=mock.sentinel.variant)
        mock_execute.assert_has_calls(calls)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_clone_hd_fail(self, mock_execute):
        mock_execute.side_effect = [
            (None, constants.VBOX_E_FILE_ERROR), (None, self._FAKE_STDERR)
        ]

        self.assertRaises(exception.DestinationDiskExists,
                          self._vbox_manage.clone_hd,
                          mock.sentinel.path, mock.sentinel.new_path)
        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.clone_hd,
                          mock.sentinel.path, mock.sentinel.new_path)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_create_vm(self, mock_execute):
        mock_execute.side_effect = [('UUID: fake-uuid', None),
                                    ('fake-output', None)]

        self.assertEqual('fake-uuid',
                         self._vbox_manage.create_vm(fake.FAKE_VM_NAME))
        self.assertIsNone(self._vbox_manage.create_vm(fake.FAKE_VM_NAME))

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_create_vm_fail(self, mock_execute):
        stdout = mock.sentinel.stdout
        mock_execute.side_effect = [(stdout, constants.VBOX_E_FILE_ERROR),
                                    (stdout, self._FAKE_STDERR)]

        self.assertRaises(exception.DestinationDiskExists,
                          self._vbox_manage.create_vm,
                          fake.FAKE_VM_NAME)
        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.create_vm,
                          fake.FAKE_VM_NAME)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_storage_ctl(self, mock_execute):
        method_input = (mock.sentinel.instance, mock.sentinel.name,
                        mock.sentinel.system_bus, mock.sentinel.controller)
        mock_execute.side_effect = [(None, self._FAKE_STDERR), (None, None)]

        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.storage_ctl, *method_input)
        self.assertIsNone(manage.VBoxManage.storage_ctl(*method_input))

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._storageattach')
    def test_storage_attach(self, mock_storage_attach):
        mock_storage_attach.side_effect = [(None, None)]
        fake_input = fake.FakeInput.storage_attach()
        fake_input['instance'] = self._instance
        fake_input['drive_type'] = constants.ALL_STORAGES[0]
        self.assertIsNone(manage.VBoxManage.storage_attach(**fake_input))
        self.assertEqual(1, mock_storage_attach.call_count)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._storageattach')
    def test_storage_attach_fail(self, mock_storage_attach):
        mock_storage_attach.side_effect = [(None, self._FAKE_STDERR)]
        fake_input = fake.FakeInput.storage_attach()
        fake_input['instance'] = self._instance

        self.assertRaises(vbox_exc.VBoxValueNotAllowed,
                          self._vbox_manage.storage_attach,
                          **fake_input)

        fake_input['drive_type'] = constants.ALL_STORAGES[0]
        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.storage_attach,
                          **fake_input)
        self.assertEqual(1, mock_storage_attach.call_count)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._storageattach')
    def test_scsi_storage_attach(self, mock_storage_attach):
        mock_storage_attach.return_value = (None, None)

        fake_input = fake.FakeInput.scsi_storage_attach(self._instance)
        self._vbox_manage.scsi_storage_attach(**fake_input)

        fake_input["connection_info"]["data"]["target_portal"] = ""
        self._vbox_manage.scsi_storage_attach(**fake_input)

        self.assertEqual(2, mock_storage_attach.call_count)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_version(self, mock_execute):
        mock_execute.side_effect = [(mock.sentinel.version, None)]
        self.assertEqual(mock.sentinel.version,
                         self._vbox_manage.version())

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_unregister_vm(self, mock_execute):
        mock_execute.side_effect = [(None, None), (None, "100%")]
        calls = [
            mock.call('unregistervm', self._instance.name, '--delete'),
            mock.call('unregistervm', self._instance.name)]

        self.assertIsNone(manage.VBoxManage.unregister_vm(self._instance))
        self.assertIsNone(manage.VBoxManage.unregister_vm(self._instance,
                                                          delete=False))
        mock_execute.assert_has_calls(calls)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_unregister_vm_fail(self, mock_execute):
        mock_execute.side_effect = [
            (None, self._FAKE_STDERR),
            (None, constants.VBOX_E_INSTANCE_NOT_FOUND)]

        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.unregister_vm, self._instance)

        self.assertRaises(exception.InstanceNotFound,
                          self._vbox_manage.unregister_vm, self._instance)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_set_vhd_uuid(self, mock_execute):
        mock_execute.side_effect = [(None, None), (None, self._FAKE_STDERR)]

        self.assertIsNone(manage.VBoxManage.set_vhd_uuid(mock.sentinel.path))
        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.set_vhd_uuid, mock.sentinel.path)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_set_property(self, mock_execute):
        mock_execute.return_value = [None, None]
        name = constants.ALL_VBOX_PROPERTIES[0]

        self._vbox_manage.set_property(name, mock.sentinel.value)
        self.assertEqual(1, mock_execute.call_count)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_set_property_fail(self, mock_execute):
        mock_execute.side_effect = [(None, self._FAKE_STDERR)]
        name = constants.ALL_VBOX_PROPERTIES[0]

        self.assertRaises(vbox_exc.VBoxValueNotAllowed,
                          self._vbox_manage.set_property,
                          mock.sentinel.name, mock.sentinel.value)
        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.set_property,
                          name, mock.sentinel.value)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_modify_hd(self, mock_execute):
        mock_execute.return_value = [None, None]
        field = constants.ALL_HD_FIELDS[0]

        self._vbox_manage.modify_hd(mock.sentinel.filename, field,
                                    mock.sentinel.value)
        self.assertEqual(1, mock_execute.call_count)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_modify_hd_fail(self, mock_execute):
        mock_execute.side_effect = [(None, self._FAKE_STDERR)]
        field = constants.ALL_HD_FIELDS[0]

        self.assertRaises(vbox_exc.VBoxValueNotAllowed,
                          self._vbox_manage.modify_hd,
                          mock.sentinel.filename, mock.sentinel.field)
        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.modify_hd,
                          mock.sentinel.filename, field)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._check_stderr')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_take_snapshot(self, mock_execute, mock_check_stderr):
        mock_execute.return_value = (mock.sentinel.stdout, None)
        self._vbox_manage.take_snapshot(self._instance, mock.sentinel.name,
                                        mock.sentinel.description, live=True)

        self.assertEqual(1, mock_execute.call_count)
        self.assertEqual(0, mock_check_stderr.call_count)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_take_snapshot_fail(self, mock_execute):
        mock_execute.side_effect = [(None, self._FAKE_STDERR)]

        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.take_snapshot,
                          self._instance, mock.sentinel.name)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_delete_snapshot(self, mock_execute):
        mock_execute.side_effect = [
            (mock.sentinel.stdout, None),
            (mock.sentinel.stdout, self._FAKE_STDERR),
        ]

        self.assertIsNone(manage.VBoxManage.delete_snapshot(
            self._instance, mock.sentinel.name))
        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.delete_snapshot,
                          self._instance, mock.sentinel.name)
        self.assertEqual(2, mock_execute.call_count)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_close_medium(self, mock_execute):
        mock_execute.return_value = (mock.sentinel.stdout, None)

        self._vbox_manage.close_medium(mock.sentinel.medium,
                                       mock.sentinel.path)
        mock_execute.assert_called_once_with(
            self._vbox_manage.CLOSE_MEDIUM, mock.sentinel.medium,
            mock.sentinel.path
        )
        mock_execute.reset_mock()

        self._vbox_manage.close_medium(
            mock.sentinel.medium, mock.sentinel.path, delete=True)
        mock_execute.assert_called_once_with(
            self._vbox_manage.CLOSE_MEDIUM, mock.sentinel.medium,
            mock.sentinel.path, "--delete"
        )

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_close_medium_fail(self, mock_execute):
        mock_execute.return_value = (None, self._FAKE_STDERR)

        self.assertRaises(vbox_exc.VBoxManageError,
                          self._vbox_manage.close_medium,
                          mock.sentinel.medium, mock.sentinel.path)
