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

import collections
import textwrap

import mock
from oslo.utils import units

from nova.virt.virtualbox import constants

FAKE_HD_UUID = 'fake-hd-uuid'
FAKE_VM_NAME = 'fake-vm-name'
FAKE_VM_UUID = 'fake-vm-uuid'
FAKE_HD_PATH = 'fake-hd-path.vdi'

FAKE_DISK_FORMAT = 'VDI'
FAKE_DISK_PATH = 'sata-fake-disk.vdi'

FAKE_HOST_PROCESSOR_COUNT = 8
FAKE_HOST_PROCESSOR_CORE_COUNT = 4
FAKE_HOST_MEMORY_AVAILABLE = 13213
FAKE_HOST_MEMORY_SIZE = 15926

FAKE_SYSTEM_BUS_IDE = 'fake-ide'
FAKE_SYSTEM_BUS_SATA = 'fake-sata'
FAKE_SYSTEM_BUS_SCSI = 'fake-scsi'

FAKE_TOTAL = 3
FAKE_USED = 2
FAKE_FREE = 1


class FakeVBoxManage(object):

    @staticmethod
    def hd_info():
        template = textwrap.dedent(
            """
            UUID:           {hd_uuid}
            Parent UUID:    base
            State:          created
            Type:           normal (base)
            Location:       {hd_path}
            Storage format: {hd_format}
            Format variant: dynamic default
            Capacity:       8192 MBytes
            Size on disk:   1548 MBytes
            In use by VMs:  {vm_name} (UUID: {vm_uuid})
            """
        )

        return template.format(
            hd_uuid=FAKE_HD_UUID, hd_path=FAKE_HD_PATH,
            hd_format=FAKE_DISK_FORMAT, vm_name=FAKE_VM_NAME,
            vm_uuid=FAKE_VM_UUID
        )

    @staticmethod
    def list_host_info(valid=True):
        template = textwrap.dedent(
            """
            Host Information:

            Processor online count: {processor_count}
            Processor count: {processor_count}
            Processor online core count: {processor_core_count}
            Processor core count: {processor_core_count}

            Memory size: {memory_size} MByte
            Memory available: {memory_available} MByte
            """
        )
        if valid:
            return template.format(
                processor_count=FAKE_HOST_PROCESSOR_COUNT,
                processor_core_count=FAKE_HOST_PROCESSOR_CORE_COUNT,
                memory_size=FAKE_HOST_MEMORY_SIZE,
                memory_available=FAKE_HOST_MEMORY_AVAILABLE
            )
        else:
            return template.format(
                processor_count='f',
                processor_core_count='a',
                memory_size='f',
                memory_available='e'
            )

    @staticmethod
    def list_os_types():
        return textwrap.dedent(
            """
            ID:          Other
            Description: Other/Unknown
            Family ID:   Other
            Family Desc: Other
            64 bit:      false

            ID:          Other_64
            Description: Other/Unknown (64-bit)
            Family ID:   Other
            Family Desc: Other
            64 bit:      true
            """
        )

    @staticmethod
    def network_info():
        return textwrap.dedent("""
            natnet1="nat"
            macaddress1="080027C89A78"
            cableconnected1="on"
            nic1="nat"
            nictype1="82540EM"
            nicspeed1="0"
            mtu="0"
            sockSnd="64"
            sockRcv="64"
            tcpWndSnd="64"
            tcpWndRcv="64"
            intnet2="intnet"
            macaddress2="080027EDA2BE"
            cableconnected2="on"
            nic2="intnet"
            nictype2="82540EM"
            nicspeed2="0"
            natnet3="nat"
            macaddress3="080027B24B22"
            cableconnected3="on"
            nic3="nat"
            nictype3="82540EM"
            nicspeed3="0"
            mtu="0"
            sockSnd="64"
            sockRcv="64"
            tcpWndSnd="64"
            tcpWndRcv="64"
            nic4="none"
            nic5="none"
            nic6="none"
            nic7="none"
            nic8="none"
        """)


def fake_disk_usage():
    ntuple_diskusage = collections.namedtuple('usage', 'total used free')
    total = FAKE_TOTAL * units.Gi
    used = FAKE_USED * units.Gi
    free = FAKE_FREE * units.Gi
    return ntuple_diskusage(total, used, free)


def fake_host_info():
    return {
        constants.HOST_PROCESSOR_COUNT: FAKE_HOST_PROCESSOR_COUNT,
        constants.HOST_PROCESSOR_CORE_COUNT: FAKE_HOST_PROCESSOR_CORE_COUNT,
        constants.HOST_MEMORY_AVAILABLE: FAKE_HOST_MEMORY_AVAILABLE,
        constants.HOST_MEMORY_SIZE: FAKE_HOST_MEMORY_SIZE,
    }


def fake_available_resources():
    return {
        'vcpus': FAKE_HOST_PROCESSOR_COUNT,
        'memory_mb': FAKE_HOST_MEMORY_SIZE,
        'memory_mb_used': FAKE_HOST_MEMORY_SIZE - FAKE_HOST_MEMORY_AVAILABLE,
        'local_gb': FAKE_TOTAL,
        'local_gb_used': FAKE_USED,
    }


class FakeInput(object):

    @staticmethod
    def storage_attach():
        return {
            'controller': mock.sentinel.controller,
            'port': mock.sentinel.port,
            'device': mock.sentinel.device,
            'drive_type': mock.sentinel.drive_type,
            'medium': mock.sentinel.medium,
        }

    @staticmethod
    def scsi_storage_attach(instance):
        return {
            'instance': instance,
            'controller': mock.sentinel.controller,
            'port': mock.sentinel.port,
            'device': mock.sentinel.device,
            'connection_info': {
                'data': {
                    'target_lun': mock.sentinel.lun,
                    'target_portal': '127.0.0.1:1234',
                    'target_iqn': mock.sentinel.target,
                    'auth_username': mock.sentinel.username,
                    'auth_password': mock.sentinel.password,
                }
            },
            'initiator': mock.sentinel.initiator
        }

    @staticmethod
    def image_metadata(disk_format=constants.DISK_FORMAT_VDI):
        return {
            "is_public": False,
            "disk_format": disk_format.lower(),
            "container_format": "bare",
            "properties": {},
        }
