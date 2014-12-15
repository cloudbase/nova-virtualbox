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
Helper methods for getting information regarding host.
"""

import collections
import ctypes
import os
import platform
import socket

from nova.virt.virtualbox import constants
from nova.virt.virtualbox import manage
from nova.virt.virtualbox import vmutils


def get_cpus_info():
    """Get the CPU information.

    :returns: A dictionary containing the main properties
    of the central processor in the hypervisor.
    """

    cpu_info = {}
    topology = {}
    host_info = vmutils.get_host_info()
    all_infos = manage.VBoxManage.list(constants.HOST_INFO)

    topology['sockets'] = host_info[constants.HOST_PROCESSOR_COUNT]
    topology['cores'] = host_info[constants.HOST_PROCESSOR_CORE_COUNT]
    topology['threads'] = topology['sockets'] / topology['cores']

    cpu_info['topology'] = topology
    cpu_info['arch'] = 'Unknown'
    cpu_info['model'] = None
    cpu_info['vendor'] = None
    cpu_info['features'] = []

    for line in all_infos.splitlines():
        if line.startswith(constants.HOST_FIRST_CPU_DESCRIPTION):
            cpu_info['model'] = line.split(':')[1].strip()
            cpu_info['vendor'] = cpu_info['model'].split()[0]
            break

    return cpu_info


def disk_usage(path):
    """Return disk usage statistics about the given path.

    Returned valus is a named tuple with attributes 'total', 'used' and
    'free', which are the amount of total, used and free space, in bytes.
    """
    ntuple_diskusage = collections.namedtuple('usage', 'total used free')

    if platform.system() == 'Windows':
        free_bytes = ctypes.c_ulonglong(0)
        total_bytes = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            ctypes.c_wchar_p(path[0]), None, ctypes.pointer(total_bytes),
            ctypes.pointer(free_bytes))
        free = free_bytes.value
        total = total_bytes.value
        used = total - free
    else:
        status = os.statvfs(path)
        free = status.f_bavail * status.f_frsize
        total = status.f_blocks * status.f_frsize
        used = (status.f_blocks - status.f_bfree) * status.f_frsize

    return ntuple_diskusage(total, used, free)


def get_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.connect(('<broadcast>', 0))
    return sock.getsockname()[0]


def get_local_ips():
    """Returns IPv4 and IPv6 addresses, ordered by protocol family."""
    addresses_info = socket.getaddrinfo(socket.gethostname(), None, 0, 0, 0)
    addresses_info.sort()
    return [address[4][0] for address in addresses_info]
