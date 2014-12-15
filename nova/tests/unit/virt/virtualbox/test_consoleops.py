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

from nova.console import type as console_type
from nova import context
from nova import exception
from nova import test
from nova.tests.unit import fake_instance
from nova.virt.virtualbox import consoleops
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exc


class ConsoleOpsTestCase(test.NoDBTestCase):

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.list')
    def setUp(self, mock_list):
        super(ConsoleOpsTestCase, self).setUp()
        _instance_values = {
            'name': 'fake_name',
            'uuid': 'fake_uuid',
        }
        self._context = context.RequestContext('fake_user', 'fake_project')
        self._instance = fake_instance.fake_instance_obj(
            self._context, **_instance_values)

        self.flags(vrde_unique_port=True, group="virtualbox")
        self.flags(vrde_module=mock.sentinel.vrde_module, group="virtualbox")
        self.flags(remote_display=True, group="virtualbox")
        self.flags(encrypted_rdp=True, group="rdp")
        mock_list.return_value = ""
        self._console = consoleops.ConsoleOps()

    def test_get_ports(self):
        for vrde_port, expected in (("1", [1]), ("2, 3", [3, 2]),
                                    ("6, 7-8, 4, 5", [8, 7, 6, 5, 4]),
                                    ("4-5, 4-5, 4, 5", [5, 4]),
                                    ("a, 5", [5]), ("a-d, 2", [2])):
            self.flags(vrde_port=vrde_port, group="virtualbox")
            ouput = consoleops._get_ports()
            self.assertEqual(expected, ouput)

    def test_remote_display(self):
        self.assertTrue(self._console.remote_display)

    def test_vrde_module(self):
        self.assertEqual(mock.sentinel.vrde_module, self._console.vrde_module)

    @mock.patch('nova.virt.virtualbox.consoleops._get_ports')
    @mock.patch('nova.virt.virtualbox.consoleops.ConsoleOps._get_ext_packs')
    def test_load(self, mock_ext_packs, mock_get_ports):
        self._console._load()
        mock_ext_packs.assert_called_once_with()
        mock_get_ports.assert_called_once_with()

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.list')
    def test_get_ext_packs(self, mock_list):
        mock_list.return_value = ('Pack no. 0:   VNC\n'
                                  'Pack no. 1    Invalid\n')
        self._console._get_ext_packs()
        mock_list.assert_called_once_with(constants.EXTPACKS)
        self.assertEqual(['VNC'], self._console._ext_packs)

    def test_get_available_port(self):
        self._console._ports["free"] = []
        self._console._ports["available"] = []
        self._console._ports["unique"] = True
        self.assertIsNone(self._console._get_available_port())

        self._console._ports["unique"] = False
        self.assertIsNone(self._console._get_available_port())

        self._console._ports["available"] = [mock.sentinel.port]
        self.assertEqual(mock.sentinel.port,
                         self._console._get_available_port())

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.show_vm_info')
    def test_get_vrde_port(self, mock_vm_info):
        mock_vm_info.side_effect = [{}, {constants.VM_VRDE_PORT: "invalid"},
                                    {constants.VM_VRDE_PORT: 3389}]
        for _ in range(2):
            self.assertIsNone(self._console._get_vrde_port(self._instance))
        self.assertEqual(3389, self._console._get_vrde_port(self._instance))

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.modify_vrde')
    def test_setup_rdp(self, mock_modify_vrde):
        self.flags(security_method=constants.VRDE_SECURITY_RDP, group="rdp")
        self._console._setup_rdp(self._instance)
        self.assertEqual(1, mock_modify_vrde.call_count)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.modify_vrde')
    def test_setup_rdp_tls(self, mock_modify_vrde):
        self.flags(security_method=constants.VRDE_SECURITY_TLS, group="rdp")
        self._console._setup_rdp(self._instance)
        self.assertEqual(4, mock_modify_vrde.call_count)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.modify_vrde')
    def test_setup_vnc(self, mock_modify_vrde):
        self.flags(vrde_password_length=2, group="virtualbox")
        self._console._setup_vnc(self._instance)

        mock_modify_vrde.assert_called_once_with(
            instance=self._instance, field=constants.FIELD_VRDE_PROPERTY,
            value=constants.PROPERTY_VNC_PASSWORD %
            {"password": self._instance.uuid[:2]}
        )

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.set_property')
    def test_setup_host(self, mock_set_property):
        mock_set_property.side_effect = [
            vbox_exc.VBoxManageError(method="set_property", reason="testing"),
            None
        ]

        self._console._ext_packs = [mock.sentinel.vrde_module]
        self.assertFalse(self._console.setup_host())
        self.assertTrue(self._console.setup_host())

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.set_property')
    def test_setup_host_fail(self, mock_set_property):
        self._console._remote_display = False
        self.assertIsNone(self._console.setup_host())
        self.assertEqual(0, mock_set_property.call_count)

        self._console._remode_display = True
        self._console._vrde_module = mock.sentinel.vrde_module
        self.assertIsNone(self._console.setup_host())
        self.assertEqual(0, mock_set_property.call_count)

    @mock.patch('nova.virt.virtualbox.consoleops.ConsoleOps.'
                '_setup_rdp')
    @mock.patch('nova.virt.virtualbox.consoleops.ConsoleOps.'
                '_setup_vnc')
    @mock.patch('nova.virt.virtualbox.consoleops.ConsoleOps.'
                '_get_available_port')
    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.modify_vrde')
    def test_prepare_instance(self, mock_modify_vrde, mock_get_port,
                              mock_setup_vnc, mock_setup_rdp):
        mock_get_port.return_value = mock.sentinel.port
        calls = [mock.call(instance=self._instance,
                           field=constants.FIELD_VRDE_SERVER,
                           value=constants.ON),
                 mock.call(instance=self._instance,
                           field=constants.FIELD_VRDE_PORT,
                           value=mock.sentinel.port)]

        self._console._remode_display = True
        self._console._vrde_module = constants.EXTPACK_VNC

        self._console.prepare_instance(self._instance)
        mock_modify_vrde.assert_has_calls(calls)
        mock_setup_vnc.assert_called_once_with(self._instance)

        self._console._vrde_module = constants.EXTPACK_RDP
        self._console.prepare_instance(self._instance)
        mock_setup_rdp.assert_called_once_with(self._instance)

    @mock.patch('nova.virt.virtualbox.manage.VBoxManage.modify_vrde')
    def test_prepare_instance_vrde_off(self, mock_modify_vrde):
        self._console._remote_display = False
        self._console.prepare_instance(self._instance)
        mock_modify_vrde.assert_called_once_with(
            instance=self._instance, field=constants.FIELD_VRDE_SERVER,
            value=constants.OFF)

    @mock.patch('nova.virt.virtualbox.consoleops.ConsoleOps._get_vrde_port')
    def test_cleanup(self, mock_get_vrde_port):
        mock_get_vrde_port.return_value = mock.sentinel.port

        self._console._ports['free'] = []
        self._console._ports['unique'] = False
        self._console.cleanup(self._instance)
        self.assertEqual(0, len(self._console._ports['free']))

        self._console._ports['unique'] = True
        self._console.cleanup(self._instance)
        self.assertEqual([mock.sentinel.port], self._console._ports['free'])

    @mock.patch('nova.virt.virtualbox.consoleops.ConsoleOps._get_vrde_port')
    @mock.patch('nova.virt.virtualbox.hostops.get_host_ip_address')
    def test_get_vnc_console(self, mock_get_ip, mock_vrde_port):
        self._console._vrde_module = constants.EXTPACK_VNC
        mock_get_ip.return_value = mock.sentinel.ip
        mock_vrde_port.side_effect = [mock.sentinel.port, None]

        self.assertIsInstance(self._console.get_vnc_console(self._instance),
                              console_type.ConsoleVNC)
        self.assertRaises(exception.ConsoleTypeUnavailable,
                          self._console.get_vnc_console,
                          self._instance)

    def test_get_vnc_console_fail(self):
        self._console._vrde_module = constants.EXTPACK_RDP
        self.assertRaises(exception.ConsoleTypeUnavailable,
                          self._console.get_vnc_console,
                          self._instance)

    @mock.patch('nova.virt.virtualbox.consoleops.ConsoleOps._get_vrde_port')
    @mock.patch('nova.virt.virtualbox.hostops.get_host_ip_address')
    def test_get_rdp_console(self, mock_get_ip, mock_vrde_port):
        self._console._vrde_module = constants.EXTPACK_RDP
        mock_get_ip.return_value = mock.sentinel.ip
        mock_vrde_port.side_effect = [mock.sentinel.port, None]

        self.assertIsInstance(self._console.get_rdp_console(self._instance),
                              console_type.ConsoleRDP)
        self.assertRaises(exception.ConsoleTypeUnavailable,
                          self._console.get_rdp_console,
                          self._instance)

    def test_get_rdp_console_fail(self):
        self._console._vrde_module = constants.EXTPACK_VNC
        self.assertRaises(exception.ConsoleTypeUnavailable,
                          self._console.get_rdp_console,
                          self._instance)
