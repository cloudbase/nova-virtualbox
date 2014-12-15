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

from nova import exception
from nova import test
from nova.tests.unit import fake_instance
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exception
from nova.virt.virtualbox import vmops


class VBoxOperationTestCase(test.NoDBTestCase):

    _FAKE_VM_NAME = 'fake-vm'
    _FAKE_VM_UUID = 'fake-vm-uuid'
    _FAKE_POWER_STATE = constants.POWER_STATE['running']
    _FAKE_MAC_ADDRESS = 'aa:bb:cc:dd'

    def setUp(self):
        super(VBoxOperationTestCase, self).setUp()
        instance_values = {
            'id': 1,
            'name': self._FAKE_VM_NAME,
            'uuid': self._FAKE_VM_UUID,
            'power_state': self._FAKE_POWER_STATE,
            'root_gb': 8,
            'ephemeral_gb': 1,
        }

        self._context = 'fake-context'
        self._instance = fake_instance.fake_instance_obj(self._context,
                                                         **instance_values)
        self._vbox_ops = vmops.VBoxOperation()

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.list')
    def test_inaccessible_vms(self, mock_list):
        mock_list.side_effect = [
            '"<inaccessible>" %(fake_uuid)s' % {
                'fake_uuid': self._FAKE_VM_UUID},
            'invalid-line']

        self.assertEqual([self._FAKE_VM_UUID],
                         self._vbox_ops._inaccessible_vms())
        self.assertEqual([], self._vbox_ops._inaccessible_vms())

    @mock.patch('os.path.exists')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.close_medium')
    @mock.patch('nova.virt.virtualbox.vhdutils.get_hard_disks')
    def test_init_host(self, mock_get_hard_disks, mock_close_medium,
                       mock_exists):
        mock_exists.return_value = False
        mock_get_hard_disks.return_value = {
            mock.sentinel.uuid: {
                constants.VHD_PATH: mock.sentinel.path,
                constants.VHD_STATE: constants.VHD_STATE_INACCESSIBLE,
            }
        }
        self._vbox_ops.init_host()

        mock_close_medium.assert_called_once_with(constants.MEDIUM_DISK,
                                                  mock.sentinel.uuid)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.list')
    def test_list_vms(self, mock_list):
        mock_list.side_effect = [
            '"{fake_vm}" {{{fake_uuid}}}'.format(fake_vm=self._FAKE_VM_NAME,
                                                 fake_uuid=self._FAKE_VM_UUID),
            'invalid-line']

        self.assertEqual({self._FAKE_VM_NAME: self._FAKE_VM_UUID},
                         self._vbox_ops._list_vms())
        self.assertEqual({}, self._vbox_ops._list_vms())

    @mock.patch('nova.virt.virtualbox.vmops.VBoxOperation._list_vms')
    def test_list_instances(self, mock_list_vms):
        mock_list_vms.return_value = {self._FAKE_VM_NAME: self._FAKE_VM_UUID}

        self.assertEqual([self._FAKE_VM_NAME], self._vbox_ops.list_instances())

    @mock.patch('nova.virt.virtualbox.vmops.VBoxOperation._list_vms')
    def test_list_instance_uuids(self, mock_list_vms):
        mock_list_vms.return_value = {self._FAKE_VM_NAME: self._FAKE_VM_UUID}

        self.assertEqual([self._FAKE_VM_UUID],
                         self._vbox_ops.list_instance_uuids())

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.list')
    def test_instance_exists(self, mock_list):
        mock_list.side_effect = [
            '"fake_vm1" {fake_uuid1}\n"fake_vm2": {fake_uuid2}\n',
            'invalid-line',
            '"{fake_vm}" {{{fake_uuid}}}'.format(fake_vm=self._instance.name,
                                                 fake_uuid=self._FAKE_VM_UUID)
        ]
        self.assertFalse(self._vbox_ops.instance_exists(self._instance))
        self.assertFalse(self._vbox_ops.instance_exists(self._instance))
        self.assertTrue(self._vbox_ops.instance_exists(self._instance))

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.show_vm_info')
    def test_get_info(self, mock_vm_info):
        mock_vm_info.return_value = {
            constants.VM_POWER_STATE: constants.STATE_POWER_OFF,
            constants.VM_CPUS: mock.sentinel.cpus,
            constants.VM_MEMORY: mock.sentinel.memory
        }
        response = self._vbox_ops.get_info(self._instance)

        mock_vm_info.assert_called_once_with(self._instance)
        self.assertEqual(mock.sentinel.cpus, response.num_cpu)
        self.assertEqual(mock.sentinel.memory, response.mem_kb)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.control_vm')
    def test_pause(self, mock_control_vm):
        self._vbox_ops.pause(self._instance)

        mock_control_vm.assert_called_once_with(self._instance,
                                                constants.STATE_PAUSE)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.control_vm')
    def test_unpause(self, mock_control_vm):
        self._vbox_ops.unpause(self._instance)

        mock_control_vm.assert_called_once_with(self._instance,
                                                constants.STATE_RESUME)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.control_vm')
    def test_suspend(self, mock_control_vm):
        self._vbox_ops.suspend(self._instance)

        mock_control_vm.assert_called_once_with(self._instance,
                                                constants.STATE_SUSPEND)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.start_vm')
    def test_resume(self, mock_start_vm):
        self._vbox_ops.resume(self._instance)

        mock_start_vm.assert_called_once_with(self._instance)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.control_vm')
    @mock.patch('nova.virt.virtualbox.vmutils.soft_shutdown')
    def test_power_off(self, mock_shutdown, mock_control_vm):
        mock_shutdown.return_value = True

        self._vbox_ops.power_off(self._instance)
        self.assertEqual(0, mock_shutdown.call_count)
        mock_control_vm.assert_called_once_with(self._instance,
                                                constants.STATE_POWER_OFF)
        mock_control_vm.reset_mock()

        self._vbox_ops.power_off(self._instance, timeout=1)
        self.assertEqual(0, mock_control_vm.call_count)
        self.assertEqual(1, mock_shutdown.call_count)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.control_vm')
    @mock.patch('nova.virt.virtualbox.vmutils.soft_shutdown')
    def test_power_off_fail_shutdown(self, mock_shutdown, mock_control_vm):
        mock_shutdown.side_effect = [
            exception.InstanceInvalidState(
                instance_uuid=self._instance.uuid,
                attr=None, state=None, method=None),
            False]

        self._vbox_ops.power_off(self._instance, timeout=1)
        mock_control_vm.assert_called_once_with(self._instance,
                                                constants.STATE_POWER_OFF)
        self._vbox_ops.power_off(self._instance, timeout=1)
        self.assertEqual(2, mock_control_vm.call_count)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.start_vm')
    def test_power_on(self, mock_start_vm):
        self._vbox_ops.power_on(self._instance)

        mock_start_vm.assert_called_once_with(self._instance)

    @mock.patch('nova.virt.virtualbox.vmops.VBoxOperation.power_on')
    @mock.patch('nova.virt.virtualbox.vmutils.soft_shutdown')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.control_vm')
    def test_reboot(self, mock_control_vm, mock_shutdown, mock_power_on):
        mock_shutdown.return_value = True

        self._vbox_ops.reboot(self._instance)
        mock_control_vm.assert_called_once_with(self._instance,
                                                constants.STATE_RESET)
        self.assertEqual(0, mock_shutdown.call_count)
        mock_control_vm.reset_mock()

        self._vbox_ops.reboot(self._instance,
                              reboot_type=constants.REBOOT_SOFT)
        self.assertEqual(1, mock_shutdown.call_count)
        self.assertEqual(1, mock_power_on.call_count)
        self.assertEqual(0, mock_control_vm.call_count)

    @mock.patch('nova.virt.virtualbox.vmutils.soft_shutdown')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.control_vm')
    def test_reboot_shutdown_fail(self, mock_control_vm, mock_shutdown):
        mock_shutdown.return_value = False

        self._vbox_ops.reboot(self._instance,
                              reboot_type=constants.REBOOT_SOFT)

        self.assertEqual(1, mock_shutdown.call_count)
        mock_control_vm.assert_called_once_with(self._instance,
                                                constants.STATE_RESET)

    @mock.patch('nova.virt.virtualbox.vmutils.update_description')
    @mock.patch('nova.virt.virtualbox.networkutils.create_nic')
    def test_network_setup(self, mock_create_nic, mock_update_description):
        vif = {"id": mock.sentinel.id,
               "address": self._FAKE_MAC_ADDRESS}
        network_info = [vif] * 3

        self._vbox_ops._network_setup(self._instance, network_info)
        self.assertEqual(len(network_info), mock_create_nic.call_count)
        self.assertEqual(1, mock_update_description.call_count)

    @mock.patch('nova.virt.virtualbox.vhdutils.get_image_type')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.create_hd')
    @mock.patch('nova.virt.virtualbox.pathutils.root_disk_path')
    @mock.patch('nova.virt.virtualbox.vhdutils.disk_info')
    @mock.patch('nova.virt.virtualbox.imagecache.get_cached_image')
    def test_create_root_disk(self, mock_get_cached_image, mock_disk_info,
                              mock_root_disk, mock_create_hd,
                              mock_get_image_type):
        self.flags(use_cow_images=True)
        mock_get_image_type.return_value = mock.sentinel.image_type
        mock_get_cached_image.return_value = mock.sentinel.cached_image
        mock_root_disk.return_value = mock.sentinel.root_disk
        mock_disk_info.return_value = {
            constants.VHD_IMAGE_TYPE: mock.sentinel.image_type
        }

        root_disk = self._vbox_ops.create_root_disk(self._context,
                                                    self._instance)

        mock_disk_info.assert_called_once_with(mock.sentinel.cached_image)
        mock_root_disk.assert_called_once_with(
            self._instance, disk_format=mock.sentinel.image_type)
        mock_create_hd.assert_called_once_with(
            filename=mock.sentinel.root_disk,
            # disk_format=mock.sentinel.image_type,
            variant=constants.VARIANT_STANDARD,
            parent=mock.sentinel.cached_image
        )
        self.assertEqual(mock.sentinel.root_disk, root_disk)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.modify_hd')
    @mock.patch('nova.virt.virtualbox.vhdutils.is_resize_required')
    @mock.patch('nova.virt.virtualbox.vhdutils.get_image_type')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.clone_hd')
    @mock.patch('nova.virt.virtualbox.pathutils.root_disk_path')
    @mock.patch('nova.virt.virtualbox.vhdutils.disk_info')
    @mock.patch('nova.virt.virtualbox.imagecache.get_cached_image')
    def test_create_root_disk_cloned(self, mock_get_cached_image,
                                     mock_disk_info, mock_root_disk,
                                     mock_clone_hd, mock_get_image_type,
                                     mock_is_resize_required, mock_modify_hd):
        self.flags(use_cow_images=False)
        mock_is_resize_required.return_value = True
        mock_get_cached_image.return_value = mock.sentinel.cached_image
        mock_root_disk.return_value = mock.sentinel.root_disk
        mock_get_image_type.return_value = constants.DISK_FORMAT_VHD
        mock_disk_info.return_value = {
            constants.VHD_IMAGE_TYPE: constants.DISK_FORMAT_VHD,
            constants.VHD_CAPACITY: 8 * units.Gi
        }

        root_disk = self._vbox_ops.create_root_disk(self._context,
                                                    self._instance)

        mock_disk_info.assert_called_once_with(mock.sentinel.cached_image)
        mock_root_disk.assert_called_once_with(
            self._instance, disk_format=constants.DISK_FORMAT_VHD)
        mock_clone_hd.assert_called_once_with(
            vhd_path=mock.sentinel.cached_image,
            new_vdh_path=mock.sentinel.root_disk,
            disk_format=constants.DISK_FORMAT_VHD,
            variant=constants.VARIANT_STANDARD
        )
        mock_is_resize_required.assert_called_once_with(
            disk_path=mock.sentinel.root_disk, old_size=8192,
            new_size=8192, instance=self._instance)
        mock_modify_hd.assert_called_once_with(
            mock.sentinel.root_disk, constants.FIELD_HD_RESIZE_MB,
            8192)
        self.assertEqual(mock.sentinel.root_disk, root_disk)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.modify_hd')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.create_hd')
    @mock.patch('nova.virt.virtualbox.pathutils.ephemeral_vhd_path')
    def test_create_ephemeral_disk(self, mock_ephemeral_vhd_path,
                                   mock_create_hd, mock_modify_hd):
        mock_ephemeral_vhd_path.return_value = mock.sentinel.eph_vhd_path
        eph_vhd_path = self._vbox_ops.create_ephemeral_disk(self._instance)

        mock_create_hd.assert_called_once_with(
            filename=mock.sentinel.eph_vhd_path,
            size=self._instance.ephemeral_gb * units.Ki,
            disk_format=constants.DEFAULT_DISK_FORMAT,
            variant=constants.VARIANT_STANDARD
        )

        mock_modify_hd.assert_called_once_with(
            filename=mock.sentinel.eph_vhd_path,
            field=constants.FIELD_HD_TYPE,
            value=constants.VHD_TYPE_IMMUTABLE
        )

        # mock_modify_hd.assert_called_once_with(
        #     filename=mock.sentinel.eph_vhd_path,
        #     field=constants.FIELD_HD_AUTORESET,
        #     value=constants.ON)

        self.assertEqual(mock.sentinel.eph_vhd_path, eph_vhd_path)

    def test_create_ephemeral_disk_fail(self):
        self._instance.ephemeral_gb = 0

        self.assertIsNone(self._vbox_ops.create_ephemeral_disk(
            self._instance))

    @mock.patch('os.path.dirname')
    @mock.patch('nova.virt.virtualbox.pathutils.instance_basepath')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.create_vm')
    @mock.patch('nova.virt.virtualbox.vmutils.set_cpus')
    @mock.patch('nova.virt.virtualbox.vmutils.set_memory')
    @mock.patch('nova.virt.virtualbox.vmutils.set_os_type')
    @mock.patch('nova.virt.virtualbox.vmops.VBoxOperation._network_setup')
    def test_create_instance(self, mock_network, mock_os_type, mock_memory,
                             mock_cpus, mock_create_vm, mock_basepath,
                             mock_dirname):
        mock_basepath.return_value = mock.sentinel.path
        mock_dirname.return_value = mock.sentinel.dirname
        image_meta = {'properties': {'os_type': mock.sentinel.os_type}}

        self._vbox_ops.create_instance(self._instance, image_meta,
                                       mock.sentinel.network_info)

        mock_basepath.assert_called_once_with(self._instance,
                                              action=constants.PATH_DELETE)
        mock_dirname.assert_called_once_with(mock.sentinel.path)
        mock_os_type.assert_called_once_with(self._instance,
                                             mock.sentinel.os_type)
        mock_memory.assert_called_once_with(self._instance)
        mock_cpus.assert_called_once_with(self._instance)
        mock_network.assert_called_once_with(self._instance,
                                             mock.sentinel.network_info)
        self.assertEqual(1, mock_create_vm.call_count)

    @mock.patch('nova.virt.virtualbox.volumeops.VolumeOperations'
                '.attach_volumes')
    @mock.patch('nova.virt.virtualbox.volumeops.VolumeOperations'
                '.attach_storage')
    @mock.patch('nova.virt.virtualbox.vmutils.set_storage_controller')
    def test_storage_setup(self, mock_set_controller, mock_attach_storage,
                           mock_attach_volumes,):
        self._vbox_ops.storage_setup(self._instance, mock.sentinel.root_disk,
                                     mock.sentinel.ephemeral,
                                     mock.sentinel.block_device_info)

        mock_set_controller.assert_has_calls([
            mock.call(self._instance, constants.SYSTEM_BUS_SATA),
            mock.call(self._instance, constants.SYSTEM_BUS_SCSI)
        ])

        mock_attach_storage.assert_has_calls([
            mock.call(instance=self._instance, port=0, device=0,
                      controller=constants.SYSTEM_BUS_SATA.upper(),
                      drive_type=constants.STORAGE_HDD,
                      medium=mock.sentinel.root_disk),
            mock.call(instance=self._instance, port=1, device=0,
                      controller=constants.SYSTEM_BUS_SATA.upper(),
                      drive_type=constants.STORAGE_HDD,
                      medium=mock.sentinel.ephemeral),
        ])
        mock_attach_volumes.assert_called_once_with(
            self._instance, mock.sentinel.block_device_info, ebs_root=False)

    @mock.patch('nova.virt.virtualbox.pathutils.instance_basepath')
    @mock.patch('nova.virt.virtualbox.vmutils.get_power_state')
    @mock.patch('nova.virt.virtualbox.vmops.VBoxOperation.instance_exists')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.control_vm')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.unregister_vm')
    def test_destroy(self, mock_unregister, mock_control_vm, mock_exists,
                     mock_power_state, mock_basepath):
        mock_exists.side_effect = [False, True]
        mock_power_state.side_effect = [
            mock.sentinel.power_state, constants.STATE_POWER_OFF,
        ]

        self._vbox_ops.destroy(self._instance)
        mock_exists.assert_called_once_with(self._instance)
        self.assertEqual(0, mock_power_state.call_count)
        mock_exists.reset_mock()

        self._vbox_ops.destroy(self._instance)
        mock_exists.assert_called_once_with(self._instance)
        mock_power_state.assert_called_once_with(self._instance)
        mock_control_vm.assert_called_once_with(self._instance,
                                                constants.STATE_POWER_OFF)
        mock_unregister.assert_called_once_with(self._instance, delete=True)
        mock_basepath.assert_called_once_with(
            self._instance, action=constants.PATH_DELETE)

    @mock.patch('nova.virt.virtualbox.vmutils.get_power_state')
    @mock.patch('nova.virt.virtualbox.vmops.VBoxOperation.instance_exists')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.unregister_vm')
    def test_destroy_fail(self, mock_unregister, mock_exists,
                          mock_power_state):
        mock_exists.return_value = True
        mock_power_state.return_value = constants.STATE_POWER_OFF
        mock_unregister.side_effect = [
            vbox_exception.VBoxManageError(method="unregistervm",
                                           reason="fake-error")]
        self.assertRaises(vbox_exception.VBoxManageError,
                          self._vbox_ops.destroy, self._instance)
        mock_exists.assert_called_once_with(self._instance)
        mock_power_state.assert_called_once_with(self._instance)

    @mock.patch('nova.virt.virtualbox.volumeutils.ebs_root_in_block_devices')
    @mock.patch('nova.virt.virtualbox.vmops.VBoxOperation.storage_setup')
    @mock.patch('nova.virt.virtualbox.vmops.VBoxOperation'
                '.create_ephemeral_disk')
    @mock.patch('nova.virt.virtualbox.vmops.VBoxOperation'
                '.create_root_disk')
    @mock.patch('nova.virt.virtualbox.vmops.VBoxOperation.create_instance')
    @mock.patch('nova.virt.virtualbox.vmops.VBoxOperation.instance_exists')
    def test_spawn(self, mock_instance_exists, mock_create_instance,
                   mock_create_root, mock_create_ephemeral,
                   mock_storage_setup, mock_ebs_root_in_block):
        mock_instance_exists.return_value = False
        mock_ebs_root_in_block.return_value = False
        mock_create_ephemeral.return_value = mock.sentinel.ephemeral
        mock_create_root.return_value = mock.sentinel.root_disk

        self._vbox_ops.spawn(self._context, self._instance,
                             mock.sentinel.image_meta,
                             mock.sentinel.injected_files,
                             mock.sentinel.admin_password,
                             mock.sentinel.network_info,
                             mock.sentinel.block_device_info)

        mock_create_instance.assert_called_once_with(
            self._instance, mock.sentinel.image_meta,
            mock.sentinel.network_info)
        mock_create_ephemeral.assert_called_once_with(self._instance)
        mock_create_root.assert_called_once_with(self._context, self._instance)
        mock_storage_setup.assert_called_once_with(
            self._instance, mock.sentinel.root_disk, mock.sentinel.ephemeral,
            mock.sentinel.block_device_info)

    @mock.patch('nova.virt.virtualbox.vmops.VBoxOperation.destroy')
    @mock.patch('nova.virt.virtualbox.vmops.VBoxOperation.create_instance')
    @mock.patch('nova.virt.virtualbox.vmops.VBoxOperation.instance_exists')
    def test_spawn_fail(self, mock_instance_exists, mock_create_instance,
                        mock_destroy):
        mock_instance_exists.side_effect = [True, False]
        mock_create_instance.side_effect = [
            vbox_exception.VBoxManageError(method="createvm", reason="n/a")
        ]

        self.assertRaises(exception.InstanceExists,
                          self._vbox_ops.spawn,
                          self._context, self._instance,
                          mock.sentinel.image_meta,
                          mock.sentinel.injected_files,
                          mock.sentinel.admin_password,
                          mock.sentinel.network_info,
                          mock.sentinel.block_device_info)

        self.assertRaises(vbox_exception.VBoxManageError,
                          self._vbox_ops.spawn,
                          self._context, self._instance,
                          mock.sentinel.image_meta,
                          mock.sentinel.injected_files,
                          mock.sentinel.admin_password,
                          mock.sentinel.network_info,
                          mock.sentinel.block_device_info)
        mock_destroy.assert_called_once_with(self._instance)
