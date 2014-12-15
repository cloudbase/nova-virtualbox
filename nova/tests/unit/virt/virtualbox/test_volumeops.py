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

from nova import exception
from nova import test
from nova.tests.unit import fake_instance
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exc
from nova.virt.virtualbox import volumeops


class VolumeOperationsTestCase(test.NoDBTestCase):

    def setUp(self):
        super(VolumeOperationsTestCase, self).setUp()
        instance_values = {
            'name': 'fake_name',
            'uuid': 'fake_uuid',
        }

        self._context = 'fake-context'
        self._instance = fake_instance.fake_instance_obj(self._context,
                                                         **instance_values)
        self.flags(my_ip=mock.sentinel.ip)
        self._volumeops = volumeops.VolumeOperations()

    def test_get_volume_driver(self):
        connection_info = {'driver_volume_type': mock.sentinel.driver_name}
        self._volumeops.volume_drivers = {
            mock.sentinel.driver_name: mock.sentinel.driver}

        driver = self._volumeops._get_volume_driver(
            connection_info=connection_info)
        self.assertEqual(mock.sentinel.driver, driver)

    def test_get_volume_driver_fail(self):
        self.assertRaises(exception.VolumeDriverNotFound,
                          self._volumeops._get_volume_driver)

    @mock.patch('platform.node')
    @mock.patch('nova.virt.virtualbox.volumeops.ISCSIVolumeDriver'
                '.get_initiator')
    def test_get_volume_connector(self, mock_get_initiator, mock_node):
        mock_get_initiator.return_value = mock.sentinel.initiator
        mock_node.return_value = mock.sentinel.node
        volume_connector = {
            'ip': mock.sentinel.ip,
            'host': mock.sentinel.node,
            'initiator': mock.sentinel.initiator,
        }

        connector = self._volumeops.get_volume_connector(self._instance)
        mock_get_initiator.assert_called_once_with(self._instance)
        self.assertEqual(volume_connector, connector)

    @mock.patch('nova.virt.virtualbox.volumeops.VolumeOperations'
                '.attach_volume')
    @mock.patch('nova.virt.driver.block_device_info_get_mapping')
    def test_attach_volumes(self, mock_bdinfo_get_mapping,
                            mock_attach_volume):
        device_count = 3
        mock_bdinfo_get_mapping.return_value = [
            {'connection_info': mock.sentinel.connection_info}
        ] * device_count

        self._volumeops.attach_volumes(self._instance, mock.sentinel.bdinfo,
                                       ebs_root=True)

        mock_bdinfo_get_mapping.assert_called_once_with(mock.sentinel.bdinfo)
        self.assertEqual(device_count, mock_attach_volume.call_count)

    @mock.patch('nova.virt.virtualbox.volumeops.VolumeOperations'
                '._get_volume_driver')
    def test_attach_volume(self, mock_get_volume_driver):
        volume_driver = mock.MagicMock()
        mock_get_volume_driver.return_value = volume_driver

        self._volumeops.attach_volume(
            self._instance, mock.sentinel.connection_info, ebs_root=False)

        volume_driver.attach_volume.assert_called_once_with(
            self._instance, mock.sentinel.connection_info, False
        )

    @mock.patch('nova.virt.virtualbox.volumeops.VolumeOperations'
                '._get_volume_driver')
    def test_detach_volume(self, mock_get_volume_driver):
        volume_driver = mock.MagicMock()
        mock_get_volume_driver.return_value = volume_driver

        self._volumeops.detach_volume(
            self._instance, mock.sentinel.connection_info)

        volume_driver.detach_volume.assert_called_once_with(
            self._instance, mock.sentinel.connection_info
        )

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.storage_attach')
    def test_attach_storage(self, mock_storage_attach):
        mock_storage_attach.return_value = mock.sentinel.return_value

        response = self._volumeops.attach_storage(
            self._instance, mock.sentinel.controller, mock.sentinel.port,
            mock.sentinel.device, mock.sentinel.drive_type,
            mock.sentinel.medium)

        mock_storage_attach.assert_called_once_with(
            self._instance, mock.sentinel.controller, mock.sentinel.port,
            mock.sentinel.device, mock.sentinel.drive_type,
            mock.sentinel.medium)
        self.assertEqual(mock.sentinel.return_value, response)


class ISCSIVolumeDriverTestCase(test.NoDBTestCase):

    def setUp(self):
        super(ISCSIVolumeDriverTestCase, self).setUp()
        instance_values = {
            'name': 'fake_name',
            'uuid': 'fake_uuid',
        }

        self._context = 'fake-context'
        self._instance = fake_instance.fake_instance_obj(self._context,
                                                         **instance_values)
        self._driver = volumeops.ISCSIVolumeDriver()

    @mock.patch('platform.node')
    def test_get_initiator(self, mock_node):
        mock_node.return_value = "host_name"
        self.assertEqual("iqn.2008-04.com.sun:host_name",
                         self._driver.get_initiator(self._instance))

    @mock.patch('nova.virt.virtualbox.volumeops.ISCSIVolumeDriver'
                '.get_initiator')
    @mock.patch('nova.virt.virtualbox.vhdutils.get_available_attach_point')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.scsi_storage_attach')
    def test_attach_volume(self, mock_scsi_storage_attach,
                           mock_get_attach_point, mock_get_initiator):
        mock_get_attach_point.return_value = (mock.sentinel.port,
                                              mock.sentinel.device)
        mock_get_initiator.return_value = mock.sentinel.initiator

        self._driver.attach_volume(self._instance,
                                   mock.sentinel.connection_info)

        mock_scsi_storage_attach.assert_called_once_with(
            self._instance, constants.SYSTEM_BUS_SCSI.upper(),
            mock.sentinel.port, mock.sentinel.device,
            mock.sentinel.connection_info, mock.sentinel.initiator
        )

    @mock.patch('nova.virt.virtualbox.volumeops.ISCSIVolumeDriver'
                '.detach_volume')
    @mock.patch('nova.virt.virtualbox.volumeops.ISCSIVolumeDriver'
                '.get_initiator')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.scsi_storage_attach')
    def test_attach_volume_fail(self, mock_scsi_storage_attach,
                                mock_get_initiator, mock_detach_volume):

        mock_get_initiator.return_value = mock.sentinel.initiator
        mock_scsi_storage_attach.side_effect = [
            vbox_exc.VBoxException(details="n/a")]

        self.assertRaises(vbox_exc.VBoxException,
                          self._driver.attach_volume,
                          self._instance, mock.sentinel.connection_info,
                          ebs_root=True)
        mock_detach_volume.assert_called_once_with(
            self._instance, mock.sentinel.connection_info)

    @mock.patch('nova.virt.virtualbox.volumeops.ISCSIVolumeDriver'
                '.get_initiator')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.scsi_storage_attach')
    def test_attach_volume_ebs_root(self, mock_scsi_storage_attach,
                                    mock_get_initiator):
        mock_get_initiator.return_value = mock.sentinel.initiator
        self._driver.attach_volume(self._instance,
                                   mock.sentinel.connection_info,
                                   ebs_root=True)

        mock_scsi_storage_attach.assert_called_once_with(
            self._instance, constants.SYSTEM_BUS_SATA.upper(),
            0, 0, mock.sentinel.connection_info, mock.sentinel.initiator
        )
