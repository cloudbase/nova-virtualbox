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

from eventlet import timeout as etimeout
import mock

from nova import exception
from nova import test
from nova.tests.unit import fake_instance
from nova.tests.unit.virt.virtualbox import fake
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exception
from nova.virt.virtualbox import vmutils


class VMUtilsTestCase(test.NoDBTestCase):

    """Test case for the helper methods for operations related to the
    management of virtual machines records and their settings.
    """

    _FAKE_VCPUS = 4
    _FAKE_MEMORY = 2048
    _FAKE_TIMEOUT = 3

    def setUp(self):
        super(VMUtilsTestCase, self).setUp()
        instance_values = {
            'name': 'fake_name',
            'uuid': 'fake_uuid',
            'image_ref': 'fake_image_ref',
            'vcpus': self._FAKE_VCPUS,
            'memory_mb': self._FAKE_MEMORY
        }

        self._context = 'fake-context'
        self._instance = fake_instance.fake_instance_obj(self._context,
                                                         **instance_values)

    @mock.patch('nova.virt.virtualbox.vmutils.get_power_state')
    def test_wait_for_power_state_true(self, mock_get_power_state):
        desired_power_state = mock.sentinel.power_state
        mock_get_power_state.return_value = desired_power_state

        response = vmutils.wait_for_power_state(
            self._instance, desired_power_state,
            constants.SHUTDOWN_RETRY_INTERVAL)

        mock_get_power_state.assert_called_with(self._instance)
        self.assertTrue(response)

    @mock.patch('eventlet.timeout.with_timeout')
    def test_wait_for_power_state_false(self, mock_with_timeout):
        desired_power_state = mock.sentinel.power_state
        mock_with_timeout.side_effect = etimeout.Timeout()

        response = vmutils.wait_for_power_state(
            self._instance, desired_power_state,
            constants.SHUTDOWN_RETRY_INTERVAL)

        self.assertFalse(response)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.list')
    def test_get_host_info(self, mock_list):
        mock_list.return_value = fake.FakeVBoxManage.list_host_info()
        response = vmutils.get_host_info()

        self.assertEqual(fake.FAKE_HOST_PROCESSOR_COUNT,
                         response[constants.HOST_PROCESSOR_COUNT])
        self.assertEqual(fake.FAKE_HOST_PROCESSOR_CORE_COUNT,
                         response[constants.HOST_PROCESSOR_CORE_COUNT])
        self.assertEqual(fake.FAKE_HOST_MEMORY_AVAILABLE,
                         response[constants.HOST_MEMORY_AVAILABLE])
        self.assertEqual(fake.FAKE_HOST_MEMORY_SIZE,
                         response[constants.HOST_MEMORY_SIZE])

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.list')
    def test_get_host_info_default(self, mock_list):
        mock_list.return_value = fake.FakeVBoxManage.list_host_info(False)
        response = vmutils.get_host_info()

        self.assertEqual(0, response[constants.HOST_PROCESSOR_COUNT])

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.list')
    def test_get_os_types(self, mock_list):
        mock_list.return_value = fake.FakeVBoxManage.list_os_types()
        response = vmutils.get_os_types()

        self.assertEqual(2, len(response))

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.show_vm_info')
    def test_get_power_state(self, mock_vm_info):
        mock_vm_info.side_effect = [
            {constants.VM_POWER_STATE: mock.sentinel.unknown_power_state},
            {constants.VM_POWER_STATE: 'poweroff'}]

        self.assertEqual(mock.sentinel.unknown_power_state,
                         vmutils.get_power_state(self._instance))
        self.assertEqual('poweroff',
                         vmutils.get_power_state(self._instance))

    @mock.patch('nova.virt.virtualbox.vmutils.get_host_info')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.modify_vm')
    def test_set_cpus(self, mock_modify_vm, mock_host_info):
        mock_host_info.side_effect = [
            {constants.HOST_PROCESSOR_COUNT: self._FAKE_VCPUS + 1},
            {constants.HOST_PROCESSOR_COUNT: self._FAKE_VCPUS - 1}
        ]
        vmutils.set_cpus(self._instance)

        self.assertEqual(1, mock_modify_vm.call_count)
        mock_modify_vm.assert_called_with(self._instance,
                                          constants.FIELD_CPUS,
                                          self._FAKE_VCPUS)
        self.assertRaises(exception.ImageNUMATopologyCPUOutOfRange,
                          vmutils.set_cpus, self._instance)

    @mock.patch('nova.virt.virtualbox.vmutils.get_host_info')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.modify_vm')
    def test_set_memory(self, mock_modify_vm, mock_host_info):
        mock_host_info.side_effect = [
            {constants.HOST_MEMORY_AVAILABLE: self._FAKE_MEMORY + 1024},
            {constants.HOST_MEMORY_AVAILABLE: self._FAKE_MEMORY - 1024}
        ]
        vmutils.set_memory(self._instance)

        self.assertEqual(1, mock_modify_vm.call_count)
        mock_modify_vm.assert_called_with(self._instance,
                                          constants.FIELD_MEMORY,
                                          self._FAKE_MEMORY)
        self.assertRaises(exception.InsufficientFreeMemory,
                          vmutils.set_memory, self._instance)

    @mock.patch('nova.virt.virtualbox.vmutils.get_os_types')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.modify_vm')
    def test_set_os_type(self, mock_modify_vm, mock_os_types):
        mock_os_types.return_value = ['Other', 'Other_x64']
        vmutils.set_os_type(self._instance, 'fake-os')
        vmutils.set_os_type(self._instance, 'Other_x64')
        calls = [
            mock.call(self._instance, constants.FIELD_OS_TYPE,
                      constants.DEFAULT_OS_TYPE),
            mock.call(self._instance, constants.FIELD_OS_TYPE, 'Other_x64')
        ]

        mock_modify_vm.assert_has_calls(calls)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.storage_ctl')
    def test_set_storage_controller(self, mock_storage_ctl):
        vmutils.set_storage_controller(self._instance,
                                       constants.SYSTEM_BUS_SCSI)
        vmutils.set_storage_controller(self._instance,
                                       constants.SYSTEM_BUS_SATA)
        vmutils.set_storage_controller(self._instance,
                                       constants.SYSTEM_BUS_IDE)

        mock_storage_ctl.assert_has_calls([
            mock.call(
                self._instance, constants.DEFAULT_SCSI_CNAME,
                constants.SYSTEM_BUS_SCSI, constants.DEFAULT_SCSI_CONTROLLER),
            mock.call(
                self._instance, constants.DEFAULT_SATA_CNAME,
                constants.SYSTEM_BUS_SATA, constants.DEFAULT_SATA_CONTROLLER),
            mock.call(
                self._instance, constants.DEFAULT_IDE_CNAME,
                constants.SYSTEM_BUS_IDE, constants.DEFAULT_IDE_CONTROLLER),
        ])

    @mock.patch('nova.virt.virtualbox.vmutils.wait_for_power_state')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.show_vm_info')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.control_vm')
    def test_soft_shutdown(self, mock_control_vm, mock_vm_info, mock_wait):
        mock_vm_info.return_value = {constants.VM_ACPI: 'on'}
        mock_wait.return_value = True

        self.assertTrue(vmutils.soft_shutdown(self._instance))
        mock_control_vm.assert_called_once_with(self._instance,
                                                constants.ACPI_POWER_BUTTON)

    @mock.patch("time.sleep")
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.control_vm')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.show_vm_info')
    def test_soft_shutdown_fail(self, mock_vm_info, mock_control_vm,
                                mock_sleep):
        mock_vm_info.side_effect = [{constants.VM_ACPI: 'off'},
                                    {constants.VM_ACPI: 'on'}]
        mock_control_vm.side_effect = [
            vbox_exception.VBoxException('Expected fail.')]

        self.assertFalse(vmutils.soft_shutdown(self._instance))
        self.assertFalse(vmutils.soft_shutdown(self._instance, 1, 1))
        mock_control_vm.assert_called_once_with(self._instance,
                                                constants.ACPI_POWER_BUTTON)
        mock_sleep.assert_called_once_with(1)

    @mock.patch('nova.virt.virtualbox.vmutils.get_power_state')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.show_vm_info')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.control_vm')
    def test_soft_shutdown_invalid_state(self, mock_control_vm, mock_vm_info,
                                         mock_power_state):
        mock_vm_info.return_value = {constants.VM_ACPI: 'on'}
        mock_power_state.side_effect = [constants.STATE_POWER_OFF,
                                        mock.sentinel.power_state]

        mock_control_vm.side_effect = exception.InstanceInvalidState(
            attr=None, instance_uuid=self._instance.uuid,
            state='invalid-state', method='shutdown')

        self.assertTrue(vmutils.soft_shutdown(
            self._instance, self._FAKE_TIMEOUT, 1.5))
        self.assertRaises(exception.InstanceInvalidState,
                          vmutils.soft_shutdown,
                          self._instance, self._FAKE_TIMEOUT, 1.5)

    @mock.patch('nova.virt.virtualbox.vmutils.wait_for_power_state')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.show_vm_info')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.control_vm')
    def test_soft_shutdown_wait(self, mock_control_vm, mock_vm_info,
                                mock_wait):
        mock_vm_info.return_value = {constants.VM_ACPI: 'on'}
        mock_wait.side_effect = [False, True]
        self.assertTrue(vmutils.soft_shutdown(self._instance,
                                              self._FAKE_TIMEOUT, 1.5))
        mock_wait.assert_has_calls([
            mock.call(self._instance, constants.STATE_POWER_OFF, 1.5),
            mock.call(self._instance, constants.STATE_POWER_OFF,
                      self._FAKE_TIMEOUT - 1.5)])

    @mock.patch('nova.virt.virtualbox.vmutils.wait_for_power_state')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.show_vm_info')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.control_vm')
    def test_soft_shutdown_wait_timeout(self, mock_control_vm, mock_vm_info,
                                        mock_wait):
        mock_vm_info.return_value = {constants.VM_ACPI: 'on'}
        mock_wait.return_value = False
        self.assertFalse(vmutils.soft_shutdown(self._instance,
                                               self._FAKE_TIMEOUT, 1.5))
        mock_wait.assert_has_calls([
            mock.call(self._instance, constants.STATE_POWER_OFF, 1.5),
            mock.call(self._instance, constants.STATE_POWER_OFF,
                      self._FAKE_TIMEOUT - 1.5)])

    @mock.patch('oslo_serialization.jsonutils.dumps')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.modify_vm')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.show_vm_info')
    def test_set_description(self, mock_show_vm_info, mock_modify_vm,
                             mock_json_dumps):
        description = {"test": mock.sentinel.test}
        mock_json_dumps.return_value = mock.sentinel.dumps
        mock_show_vm_info.return_value = {}

        vmutils.update_description(self._instance, description)
        mock_modify_vm.assert_called_once_with(
            self._instance, constants.FIELD_DESCRIPTION,
            mock.sentinel.dumps)
        mock_json_dumps.assert_called_once_with(description)

    @mock.patch('oslo_serialization.jsonutils.loads')
    @mock.patch('oslo_serialization.jsonutils.dumps')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.modify_vm')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.show_vm_info')
    def test_update_description(self, mock_show_vm_info, mock_modify_vm,
                                mock_json_dumps, mock_json_loads):
        description = {"test": mock.sentinel.test}
        mock_json_dumps.return_value = mock.sentinel.dumps
        mock_json_loads.return_value = {"test": mock.sentinel.loads}
        mock_show_vm_info.return_value = {
            'current_description': mock.sentinel.description}

        vmutils.update_description(self._instance, description)
        mock_modify_vm.assert_called_once_with(
            self._instance, constants.FIELD_DESCRIPTION,
            mock.sentinel.dumps)
        mock_json_dumps.assert_called_once_with(description)
        mock_json_loads.assert_called_once_with(mock.sentinel.description)

    @mock.patch('oslo_serialization.jsonutils.loads')
    @mock.patch('oslo_serialization.jsonutils.dumps')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.modify_vm')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.show_vm_info')
    def test_update_description_fail(self, mock_show_vm_info, mock_modify_vm,
                                     mock_json_dumps, mock_json_loads):
        description = {"test": mock.sentinel.test}
        mock_json_loads.side_effect = [ValueError]
        mock_json_dumps.return_value = description

        vmutils.update_description(self._instance, description)
        mock_modify_vm.assert_called_once_with(
            self._instance, constants.FIELD_DESCRIPTION,
            description)
        mock_json_dumps.assert_called_once_with(description)
