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
from oslo_config import cfg

from nova import test
from nova.tests.unit.virt.virtualbox import fake
from nova.virt.virtualbox import hostops

CONF = cfg.CONF


class HostOpsTestCase(test.NoDBTestCase):

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.version')
    def test_get_hypervisor_version(self, mock_version):
        mock_version.side_effect = ['4.3.18_Ubuntur96516', '4.3.18_96516',
                                    '4.3.18.96516', '4.3.18 96516']
        for _ in range(4):
            self.assertEqual('431896516', hostops._get_hypervisor_version())

    @mock.patch('os.path.splitdrive')
    @mock.patch('nova.virt.virtualbox.hostutils.disk_usage')
    @mock.patch('nova.virt.virtualbox.pathutils.instance_dir')
    def test_get_local_hdd_info_gb(self, mock_instance_dir, mock_disk_usage,
                                   mock_splitdrive):
        mock_instance_dir.return_value = mock.sentinel.instance_path
        mock_splitdrive.side_effect = [('',), (mock.sentinel.path,)]
        mock_disk_usage.return_value = fake.fake_disk_usage()
        calls = [mock.call(mock.sentinel.instance_path),
                 mock.call(mock.sentinel.path)]
        expected = (fake.FAKE_TOTAL, fake.FAKE_FREE, fake.FAKE_USED)
        for _ in range(2):
            self.assertEqual(expected, hostops._get_local_hdd_info_gb())

        mock_disk_usage.assert_has_calls(calls)

    @mock.patch('oslo_serialization.jsonutils.dumps')
    @mock.patch('nova.virt.virtualbox.hostops._get_hypervisor_version')
    @mock.patch('nova.virt.virtualbox.hostops._get_local_hdd_info_gb')
    @mock.patch('nova.virt.virtualbox.hostutils.get_cpus_info')
    @mock.patch('nova.virt.virtualbox.vmutils.get_host_info')
    def test_get_available_resource(self, mock_host_info, mock_cpu_info,
                                    mock_hdd_info, mock_version,
                                    mock_json_utils):
        mock_host_info.return_value = fake.fake_host_info()
        mock_version.return_value = mock.sentinel.version
        mock_cpu_info.return_value = mock.sentinel.cpu_info
        mock_json_utils.return_value = mock.sentinel.cpu_info
        mock_hdd_info.return_value = (fake.FAKE_TOTAL, fake.FAKE_FREE,
                                      fake.FAKE_USED)
        expected = fake.fake_available_resources()
        response = hostops.get_available_resource()
        self.assertEqual(1, mock_host_info.call_count)
        self.assertEqual(1, mock_cpu_info.call_count)
        self.assertEqual(1, mock_hdd_info.call_count)
        mock_json_utils.assert_has_calls(mock.call(mock.sentinel.cpu_info))
        for key, value in expected.items():
            self.assertEqual(value, response[key])

    @mock.patch('nova.virt.virtualbox.hostutils.get_local_ips')
    def test_get_host_ip_address(self, mock_local_ips):
        mock_local_ips.return_value = [mock.sentinel.ip]
        CONF.set_override('my_ip', None)

        self.assertEqual(mock.sentinel.ip, hostops.get_host_ip_address())
        mock_local_ips.assert_called_once_with()
