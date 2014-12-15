# Copyright (c) 2015 Cloudbase Solutions Srl
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
Utility class for network related operations.
"""

from nova import exception
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import manage


def mac_address(address):
    if '-' in address:
        address = address.replace('-', '')
    elif ':' in address:
        address = address.replace(':', '')

    return address.upper()


def get_nic_status(instance):
    """Get status for all the available NIC for received instance."""
    nic_status = {}
    instance_info = manage.VBoxManage.show_vm_info(instance)
    for key, value in instance_info.items():
        if key.startswith('nic'):
            try:
                index = int(key.replace('nic', ''))
            except ValueError:
                continue
            nic_status[index] = False if value is None else True
    return nic_status


def get_available_nic(instance):
    """Return the index of the first disabled nic."""
    nic_status = get_nic_status(instance)
    for key, value in nic_status.items():
        if not value:
            return key
    return None


def create_nic(instance, vif):
    """Create a (synthetic) nic and attach it to the vm."""
    nic_index = get_available_nic(instance)
    if not nic_index:
        raise exception.NoMoreNetworks()

    # Create a NIC not connected to the host
    manage.VBoxManage.modify_network(instance=instance, index=nic_index,
                                     field=constants.FIELD_NIC,
                                     value=constants.DEFAULT_NIC_MODE)

    # Set networking hardware
    manage.VBoxManage.modify_network(instance=instance, index=nic_index,
                                     field=constants.FIELD_NIC_TYPE,
                                     value=constants.DEFAULT_NIC_TYPE)

    # Set mac adress
    manage.VBoxManage.modify_network(instance=instance, index=nic_index,
                                     field=constants.FILED_MAC_ADDRESS,
                                     value=mac_address(vif['address']))

    # Connect NIC cable
    manage.VBoxManage.modify_network(instance=instance, index=nic_index,
                                     field=constants.FIELD_CABLE_CONNECTED,
                                     value=constants.ON)
