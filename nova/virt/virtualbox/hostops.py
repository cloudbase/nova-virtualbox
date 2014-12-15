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

import os
import platform

from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import units

from nova.compute import arch
from nova.compute import hv_type
from nova.compute import vm_mode
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import hostutils
from nova.virt.virtualbox import manage
from nova.virt.virtualbox import pathutils
from nova.virt.virtualbox import vmutils

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CONF.import_opt('instances_path', 'nova.compute.manager')
CONF.import_opt('my_ip', 'nova.netconf')


def _get_hypervisor_version():
    version = manage.VBoxManage.version()
    numeric_version = [number if number.isdigit() else ''
                       for number in version]
    return "".join(numeric_version)


def _get_local_hdd_info_gb():
    path = pathutils.instance_dir(action=constants.PATH_CREATE)
    drive = os.path.splitdrive(path)[0] or path
    usage = hostutils.disk_usage(drive)

    total_gb = usage.total / units.Gi
    free_gb = usage.free / units.Gi
    used_gb = usage.used / units.Gi
    return (total_gb, free_gb, used_gb)


def get_available_resource():
    """Retrieve resource info.

    This method is called when nova-compute launches, and
    as part of a periodic task.

    :returns: dictionary describing resources
    """

    host_info = vmutils.get_host_info()
    cpu_info = hostutils.get_cpus_info()
    local_gb, _, local_gb_used = _get_local_hdd_info_gb()

    resources = {
        'vcpus': host_info[constants.HOST_PROCESSOR_COUNT],
        'memory_mb': host_info[constants.HOST_MEMORY_SIZE],
        'memory_mb_used': (host_info[constants.HOST_MEMORY_SIZE] -
                           host_info[constants.HOST_MEMORY_AVAILABLE]),
        'local_gb': local_gb,
        'local_gb_used': local_gb_used,
        'hypervisor_type': "vbox",
        'hypervisor_version': _get_hypervisor_version(),
        'hypervisor_hostname': platform.node(),
        'vcpus_used': 0,
        'cpu_info': jsonutils.dumps(cpu_info),
        'supported_instances': jsonutils.dumps([
            (arch.I686, hv_type.VBOX, vm_mode.HVM),
            (arch.X86_64, hv_type.VBOX, vm_mode.HVM)]),
        'numa_topology': None,
    }

    return resources


def get_host_ip_address():
    """Return the first available IP address."""
    host_ip = CONF.my_ip
    if not host_ip:
        host_ip = hostutils.get_local_ips()[0]
    LOG.debug("Host IP address is: %s", host_ip)
    return host_ip
