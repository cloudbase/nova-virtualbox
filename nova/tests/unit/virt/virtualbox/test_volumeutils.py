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
from nova.virt.virtualbox import volumeutils


class VolumeUtilsTestCase(test.NoDBTestCase):

    def setUp(self):
        super(VolumeUtilsTestCase, self).setUp()
        instance_values = {
            'name': 'fake_name',
            'uuid': 'fake_uuid',
            'image_ref': 'fake_image_ref'
        }

        self._context = 'fake-context'
        self._instance = fake_instance.fake_instance_obj(self._context,
                                                         **instance_values)

    def test_group_block_devices_by_type(self):
        volume1 = {'connection_info': {
            'driver_volume_type': mock.sentinel.type}}
        volume2 = {'connection_info': {
            'driver_volume_type': mock.sentinel.type}}
        block_device_mapping = [volume1, volume2]
        block_devices = volumeutils.group_block_devices_by_type(
            block_device_mapping)

        self.assertEqual({mock.sentinel.type: [volume1, volume2]},
                         block_devices)

    def test_ebs_root_in_block_devices(self):
        # TODO(alexandrucoman): Add this test
        pass

    def test_volume_in_mapping(self):
        # TODO(alexandrucoman): Add this test
        pass
