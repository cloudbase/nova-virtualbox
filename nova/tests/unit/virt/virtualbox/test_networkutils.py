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
from nova.tests.unit.virt.virtualbox import fake
from nova.virt.virtualbox import networkutils


class NetworkUtilsTestCase(test.NoDBTestCase):

    def setUp(self):
        super(NetworkUtilsTestCase, self).setUp()
        instance_values = {
            'name': 'fake_name',
            'uuid': 'fake_uuid',
        }

        self._context = 'fake-context'
        self._instance = fake_instance.fake_instance_obj(self._context,
                                                         **instance_values)

    def test_mac_address(self):
        for address in ('aa:bb', 'aa-bb'):
            self.assertEqual('AABB', networkutils.mac_address(address))

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage._execute')
    def test_get_nic_status(self, mock_vm_info):
        mock_vm_info.return_value = (fake.FakeVBoxManage.network_info(), None)
        response = networkutils.get_nic_status(self._instance)

        self.assertEqual(8, len(response))
        for index in range(3):
            self.assertTrue(response[index + 1])
        for index in range(3, 8):
            self.assertFalse(response[index + 1])

    @mock.patch('nova.virt.virtualbox.networkutils.get_nic_status')
    def test_get_available_nic(self, mock_get_nic):
        mock_get_nic.side_effect = [{1: False}, {1: True, 2: False},
                                    {1: True}]

        self.assertEqual(1, networkutils.get_available_nic(self._instance))
        self.assertEqual(2, networkutils.get_available_nic(self._instance))
        self.assertIsNone(networkutils.get_available_nic(self._instance))

    @mock.patch('nova.virt.virtualbox.networkutils.get_available_nic')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.modify_network')
    def test_create_nic(self, mock_modify_network, mock_available_nic):
        mock_available_nic.side_effect = [mock.sentinel.index, None]
        networkutils.create_nic(self._instance,
                                {'address': 'aa:aa:aa:aa'})

        self.assertEqual(4, mock_modify_network.call_count)
        self.assertRaises(exception.NoMoreNetworks, networkutils.create_nic,
                          self._instance, mock.sentinel.vif)
