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

"""
Management class for operations related to remote display.
"""

import re
import threading

from oslo_config import cfg
from oslo_log import log as logging

from nova.console import type as console_type
from nova import exception
from nova import i18n
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exc
from nova.virt.virtualbox import hostutils
from nova.virt.virtualbox import manage

REMOTE_DISPLAY = [
    cfg.BoolOpt(
        'remote_display', default=False,
        help='Enable or disable the VRDE Server.'),
    cfg.BoolOpt(
        'vrde_unique_port', default=False,
        help='Whether to use an unique port for each instance.'),
    cfg.StrOpt(
        'vrde_module', default='Oracle VM VirtualBox Extension Pack',
        help='The module used by VRDE Server'),
    cfg.IntOpt(
        'vrde_password_length', default=None,
        help='VRDE maximum length for password.'),
    cfg.StrOpt(
        'vrde_port', default='3389',
        help='A port or a range of ports the VRDE server can bind to.'),
    cfg.BoolOpt(
        'vrde_require_instance_uuid_as_password', default=False,
        help="Use the instance uuid as password for the VRDE server."),
    ]

ENCRIPTED_RDP = [
    cfg.BoolOpt(
        'encrypted_rdp', default=False,
        help='Enable or disable the rdp encryption.'),
    cfg.StrOpt(
        'security_method', default=constants.VRDE_SECURITY_RDP,
        help='The security method used for encryption. (RDP, TLS, Negotiate)'
    ),
    cfg.StrOpt(
        'server_certificate', default=None,
        help='The Server Certificate.'),
    cfg.StrOpt(
        'server_private_key', default=None,
        help='The Server Private Key.'),
    cfg.StrOpt(
        'server_ca', default=None,
        help='The Certificate Authority (CA) Certificate.'),
]

CONF = cfg.CONF
CONF.register_opts(REMOTE_DISPLAY, 'virtualbox')
CONF.register_opts(ENCRIPTED_RDP, 'rdp')
LOG = logging.getLogger(__name__)


def _get_ports():
    """Process infromation regarding ports from config and return a list of
    unique ports.
    """
    ports = []
    for group in CONF.virtualbox.vrde_port.split(','):
        if '-' not in group:
            try:
                ports.append(int(group))
            except ValueError:
                continue
        else:
            start, stop = group.split('-', 1)
            try:
                ports.extend(range(int(start), int(stop) + 1))
            except ValueError:
                continue
    return sorted(set(ports), reverse=True)


class ConsoleOps(object):

    """Management class for operations related to remote display."""

    _EXTPACK_NAME_REGEXP = r'Pack no. \d+:\s+(?P<name>.+)'

    def __init__(self):
        self._vbox_manage = manage.VBoxManage()
        self._ext_packs = []
        self._ports = {
            'available': [], 'free': [], 'used': {},
            'unique': CONF.virtualbox.vrde_unique_port
        }
        self._lock = threading.Lock()
        self._remote_display = CONF.virtualbox.remote_display
        self._vrde_module = CONF.virtualbox.vrde_module
        self._load()

    @property
    def remote_display(self):
        """VirtualBox remote desktop extension (VRDE) server status."""
        return self._remote_display

    @property
    def vrde_module(self):
        """Library witch implements the VRDE."""
        return self._vrde_module

    def _load(self):
        """Process information from hypervisor and config file."""
        if self._remote_display:
            self._get_ext_packs()
            if self._ports['unique']:
                self._ports['free'] = _get_ports()
            else:
                self._ports['available'] = _get_ports()

    def _get_ext_packs(self):
        """Get package name for each extension pack installed."""
        pack_name = re.compile(self._EXTPACK_NAME_REGEXP)
        extpacks_output = self._vbox_manage.list(constants.EXTPACKS)
        for line in extpacks_output.splitlines():
            extpack = pack_name.search(line)
            if not extpack:
                continue
            self._ext_packs.append(extpack.group('name').strip())

    def _get_available_port(self):
        """Return first available port found."""
        with self._lock:
            if not self._ports['free']:
                if self._ports['unique']:
                    return None
                if not self._ports['available']:
                    return None

                self._ports['free'] = list(self._ports['available'])

            return self._ports['free'].pop()

    def _get_vrde_port(self, instance):
        """Return the VRDE port for the received instance."""
        port = self._ports['used'].get(instance.name, None)
        if not port:
            try:
                instance_info = self._vbox_manage.show_vm_info(instance)
                port = int(instance_info[constants.VM_VRDE_PORT])
            except (ValueError, KeyError) as exc:
                LOG.debug("Failed to get port for instance: %(reason)s",
                          {"reason": exc}, instance=instance)
            except (exception.InstanceNotFound, vbox_exc.VBoxException) as exc:
                LOG.debug("Failed to get information regarding "
                          "instance: %(reason)s",
                          {"reason": exc}, instance=instance)
        return port

    def _setup_rdp(self, instance):
        """Setup the RDP VRDE module."""
        if not CONF.rdp.encrypted_rdp:
            return

        security_method = CONF.rdp.security_method
        self._vbox_manage.modify_vrde(
            instance=instance, field=constants.FIELD_VRDE_PROPERTY,
            value=constants.VRDE_SECURITY_METHOD %
            {"method": security_method})

        if security_method in (constants.VRDE_SECURITY_TLS,
                               constants.VRDE_SECURITY_NEGOTIATE):
            # NOTE(alexandrucoman): If the Security/Method property is set to
            # either Negotiate or TLS, the TLS protocol will be automatically
            # used by the server, if the client supports TLS.
            # However, in order to use TLS the server must possess
            # the Server Certificate, the Server Private Key and
            # the Certificate Authority (CA) Certificate.
            self._vbox_manage.modify_vrde(
                instance=instance, field=constants.FIELD_VRDE_PROPERTY,
                value=constants.VRDE_SECURITY_CA %
                {"path": CONF.rdp.server_ca})
            self._vbox_manage.modify_vrde(
                instance=instance, field=constants.FIELD_VRDE_PROPERTY,
                value=constants.VRDE_SECURITY_SERVER_CERT %
                {"path": CONF.rdp.server_certificate})
            self._vbox_manage.modify_vrde(
                instance=instance, field=constants.FIELD_VRDE_PROPERTY,
                value=constants.VRDE_SERCURITY_SERVER_PRIVATE_KEY %
                {"path": CONF.rdp.server_private_key})

    def _setup_vnc(self, instance):
        """Setup the VNC VRDE module."""
        password = instance.uuid
        if CONF.virtualbox.vrde_password_length:
            password = password[:CONF.virtualbox.vrde_password_length]
        self._vbox_manage.modify_vrde(
            instance=instance, field=constants.FIELD_VRDE_PROPERTY,
            value=constants.PROPERTY_VNC_PASSWORD %
            {"password": password})

    def setup_host(self):
        """Setup VirtualBox to use the received VirtualBox Remote
        Desktop Extension if `remote_display` is enabled.
        """
        if not self.remote_display:
            LOG.debug("VRDE server is disabled.")
            return

        if self.vrde_module not in self._ext_packs:
            LOG.warning(
                i18n._LW("The `%(vrde_module)s` VRDE Module is not "
                         "available."),
                {"vrde_module": self.vrde_module})
            return

        try:
            self._vbox_manage.set_property(constants.VBOX_VRDE_EXTPACK,
                                           self.vrde_module)
        except vbox_exc.VBoxManageError as exc:
            LOG.warning(
                i18n._LW("Failed to set VRDE Module `%(vrde_module)s`: "
                         "%(reason)s"),
                {"vrde_module": self.vrde_module, "reason": exc})
            return False

        LOG.info(i18n._LI("The VRDE Module used is %(vrde_module)s"),
                 {"vrde_module": self.vrde_module})
        return True

    def _enable_vrde(self, instance):
        port = self._get_available_port()
        if not port:
            raise vbox_exc.VBoxException(
                i18n._LE("No available port was found."))

        self._ports['used'][instance.name] = port
        self._vbox_manage.modify_vrde(instance=instance,
                                      field=constants.FIELD_VRDE_SERVER,
                                      value=constants.ON)
        self._vbox_manage.modify_vrde(instance=instance,
                                      field=constants.FIELD_VRDE_PORT,
                                      value=port)

        if self.vrde_module == constants.EXTPACK_VNC:
            self._setup_vnc(instance)
        elif self.vrde_module == constants.EXTPACK_RDP:
            self._setup_rdp(instance)

    def prepare_instance(self, instance):
        """Modify the instance settings in order to properly work remote
        display.
        """
        if self.remote_display:
            # Enable VRDE Server
            LOG.debug("Try to enable the VRDE Server.")
            try:
                self._enable_vrde(instance)
            except vbox_exc.VBoxException as error:
                LOG.warning(i18n._LW("Enabling VRDE Server failed: %(error)s"),
                            {"error": error})
            else:
                return

        # Disable VRDE Server
        LOG.debug("Try to disable the VRDE Server.")
        try:
            self._vbox_manage.modify_vrde(instance=instance,
                                          field=constants.FIELD_VRDE_SERVER,
                                          value=constants.OFF)
        except vbox_exc.VBoxManageError as error:
            LOG.warning(i18n._LW("Disabling VRDE Server failed: %(error)s"),
                        {"error": error})

    def cleanup(self, instance):
        """Clean up the resources allocated for the instance."""
        LOG.debug("cleanup called", instance=instance)
        with self._lock:
            self._ports['used'].pop(instance.name, None)
            port = self._get_vrde_port(instance)
            if port and self._ports['unique']:
                self._ports['free'].append(port)

    def get_vnc_console(self, instance):
        """Get connection info for a vnc console."""
        LOG.debug("get_vnc_console called", instance=instance)
        if self.remote_display and self.vrde_module == constants.EXTPACK_VNC:
            host = hostutils.get_ip()
            port = self._get_vrde_port(instance)
            if port:
                LOG.debug("VNC console: %(host)s:%(port)s",
                          {"host": host, "port": port})
                return console_type.ConsoleVNC(host=host, port=port)
            else:
                LOG.warning(i18n._LW("VNC port not found!"), instance=instance)
        else:
            LOG.warning(i18n._LW("VNC console is not available for this"
                                 " instance."),
                        instance=instance)

        raise exception.ConsoleTypeUnavailable(console_type='vnc')

    def get_rdp_console(self, instance):
        """Get connection info for a rdp console."""
        LOG.debug("get_rdp_console called", instance=instance)
        if self.remote_display and self.vrde_module == constants.EXTPACK_RDP:
            host = hostutils.get_ip()
            access_path = None if self._ports['unique'] else instance.name
            port = self._get_vrde_port(instance)
            if port:
                LOG.debug("RDP console: %(host)s:%(port)s, %(path)s",
                          {"host": host, "port": port, "path": access_path})
                return console_type.ConsoleRDP(
                    host=host, port=port, internal_access_path=access_path)
            else:
                LOG.warning(i18n._LW("RDP port not found."), instance=instance)
        else:
            LOG.warning(i18n._LW("VNC console is not available for this "
                                 "instance."),
                        instance=instance)

        raise exception.ConsoleTypeUnavailable(console_type='rdp')
