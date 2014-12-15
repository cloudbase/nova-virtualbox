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
#    under the Licenseself.

import collections

import mock

from nova import test
from nova.tests.unit.virt.virtualbox import fake
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import hostutils


class HostUtilsTestCase(test.NoDBTestCase):

    _FAKE_VENDOR = 'FakeVendor'
    _FAKE_MODEL = '{fake_vendor} FakeCPU'.format(fake_vendor=_FAKE_VENDOR)
    _FAKE_TOTAL = 4000000
    _FAKE_FREE = 400000
    _FAKE_USED = _FAKE_TOTAL - _FAKE_FREE

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.list')
    @mock.patch('nova.virt.virtualbox.vmutils.get_host_info')
    def test_get_cpus_info(self, mock_host_info, mock_list):
        mock_host_info.return_value = fake.fake_host_info()
        mock_list.return_value = "{cpu_desc_key}: {cpu_model}".format(
            cpu_desc_key=constants.HOST_FIRST_CPU_DESCRIPTION,
            cpu_model=self._FAKE_MODEL)
        expected_topology = {
            'sockets': fake.FAKE_HOST_PROCESSOR_COUNT,
            'cores': fake.FAKE_HOST_PROCESSOR_CORE_COUNT,
            'threads': (fake.FAKE_HOST_PROCESSOR_COUNT /
                        fake.FAKE_HOST_PROCESSOR_CORE_COUNT)
        }
        cpu_info = hostutils.get_cpus_info()

        self.assertEqual(self._FAKE_VENDOR, cpu_info['vendor'])
        self.assertEqual(self._FAKE_MODEL, cpu_info['model'])
        self.assertEqual(expected_topology, cpu_info['topology'])

    @mock.patch('os.statvfs')
    @mock.patch('platform.system')
    def test_disk_usage_linux(self, mock_system, mock_statvfs):
        mock_system.return_value = 'Linux'
        mock_statvfs_response = mock.MagicMock()
        mock_statvfs_response.f_bavail = self._FAKE_FREE
        mock_statvfs_response.f_frsize = 1
        mock_statvfs_response.f_blocks = self._FAKE_TOTAL
        mock_statvfs_response.f_bfree = self._FAKE_FREE
        mock_statvfs.return_value = mock_statvfs_response
        disk_usage = hostutils.disk_usage(mock.sentinel.path)

        mock_statvfs.assert_called_once_with(mock.sentinel.path)
        self.assertEqual(self._FAKE_TOTAL, disk_usage.total)
        self.assertEqual(self._FAKE_FREE, disk_usage.free)
        self.assertEqual(self._FAKE_USED, disk_usage.used)

    @mock.patch('nova.virt.virtualbox.hostutils.ctypes')
    @mock.patch('platform.system')
    def test_disk_usage_windows(self, mock_system, mock_ctype):
        response = collections.namedtuple('response', 'value')

        mock_system.return_value = 'Windows'
        mock_ctype.c_ulonglong.side_effect = [response(self._FAKE_FREE),
                                              response(self._FAKE_TOTAL)]
        disk_usage = hostutils.disk_usage('C:')

        self.assertEqual(self._FAKE_TOTAL, disk_usage.total)
        self.assertEqual(self._FAKE_FREE, disk_usage.free)
        self.assertEqual(self._FAKE_USED, disk_usage.used)

    @mock.patch('socket.getaddrinfo')
    @mock.patch('socket.gethostname')
    def test_get_local_ips(self, mock_host_name, mock_addr_info):
        mock_host_name.return_value = mock.sentinel.hostname
        mock_addr_info.return_value = [[None, None, None, '',
                                       [mock.sentinel.ip, 0]]]

        self.assertEqual([mock.sentinel.ip], hostutils.get_local_ips())
