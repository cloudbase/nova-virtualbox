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
Constants used in virtualbox module
"""

from nova.compute import power_state


ON, OFF, DEFAULT = ('on', 'off', 'default')
DONE = "100%"

EXTPACKS = 'extpacks'
OSTYPES_INFO = 'ostypes'
RUNNINGVMS_INFO = 'runningvms'
VMS_INFO = 'vms'
HOST_INFO = 'hostinfo'
HDDS_INFO = 'hdds'

ACPI_POWER_BUTTON = 'acpipowerbutton'
ACPI_SLEEP_BUTTON = 'acpisleepbutton'

CONTROLLER_BUS_LOGIC = 'BusLogic'
CONTROLLER_LSI_LOGIC = 'LsiLogic'
CONTROLLER_LSI_LOGIC_SAS = 'LSILogicSAS'
CONTROLLER_INTEL_AHCI = 'IntelAhci'
CONTROLLER_PIIX3 = 'PIIX3'
CONTROLLER_PIIX4 = 'PIIX4'
CONTROLLER_ICH6 = 'ICH6'
CONTROLLER_I82078 = 'I82078'

DISK_FORMAT_VDI = 'VDI'
DISK_FORMAT_VHD = 'VHD'
DISK_FORMAT_VMDK = 'VMDK'

EXTPACK_VNC = 'VNC'
EXTPACK_RDP = 'Oracle VM VirtualBox Extension Pack'

FIELD_CPUS = '--cpus'
FIELD_DESCRIPTION = '--description'
FIELD_MEMORY = '--memory'
FIELD_OS_TYPE = '--ostype'

FIELD_NIC = "--nic%(index)s"
FIELD_NIC_TYPE = "--nictype%(index)s"
FIELD_CABLE_CONNECTED = "--cableconnected%(index)s"
FIELD_BRIDGE_ADAPTER = "--bridgeadapter%(index)s"
FILED_MAC_ADDRESS = "--macaddress%(index)s"

FIELD_HD_AUTORESET = '--autoreset'
FIELD_HD_COMPACT = '--compact'
FIELD_HD_RESIZE_BYTE = '--resizebyte'
FIELD_HD_RESIZE_MB = '--resize'
FIELD_HD_TYPE = '--type'

FIELD_INITIATOR = "--initiator"
FIELD_LUN = "--lun"
FIELD_PASSWORD = "--password"
FIELD_PORTAL = "--server"
FIELD_PORTAL_PORT = "--tport"
FIELD_TARGET = '--target'
FIELD_USERNAME = "--username"

FIELD_VRDE_EXTPACK = '--vrdeextpack'
FIELD_VRDE_MULTICON = '--vrdemulticon'
FIELD_VRDE_PORT = '--vrdeport'
FIELD_VRDE_SERVER = '--vrde'
FIELD_VRDE_VIDEO = '--vrdevideochannel'
FIELD_VRDE_PROPERTY = '--vrdeproperty'

PROPERTY_VNC_PASSWORD = 'VNCPassword=%(password)s'

HOST_MEMORY_AVAILABLE = 'Memory available'
HOST_MEMORY_SIZE = 'Memory size'
HOST_PROCESSOR_COUNT = 'Processor count'
HOST_PROCESSOR_CORE_COUNT = 'Processor core count'
HOST_FIRST_CPU_DESCRIPTION = 'Processor#0 description'

MEDIUM_ISCSI = 'iscsi'
MEDIUM_DISK = 'disk'
MEDIUM_DVD = 'dvd'
MEDIUM_FLOPPY = 'floppy'
MEDIUM_NONE = 'none'

NIC_MODE_NONE = 'none'
NIC_MODE_NULL = 'null'
NIC_MODE_NAT = 'nat'
NIC_MODE_BRIDGED = 'bridged'
NIC_MODE_INTNET = 'intnet'
NIC_MODE_HOSTONLY = 'hostonly'
NIC_MODE_GENERIC = 'generic'

NIC_TYPE_AM79C970A = 'Am79C970A'    # AMD PCNet PCI II
NIC_TYPE_AM79C973 = 'Am79C973'      # AMD PCNet FAST III
NIC_TYPE_82540EM = '82540EM'        # Intel PRO/1000 MT Desktop
NIC_TYPE_82543GC = '82543GC'        # Intel PRO/1000 T Server
NIC_TYPE_82545EM = '82545EM'        # Intel PRO/1000 MT Server
NIC_TYPE_VIRTIO = 'virtio'          # Paravirtualized network adapter

REBOOT_HARD = 'HARD'
REBOOT_SOFT = 'SOFT'

PATH_OVERWRITE = 'overwrite'
PATH_CREATE = 'create'
PATH_DELETE = 'delete'
PATH_EXISTS = 'exists'

SHUTDOWN_RETRY_INTERVAL = 5

STATE_PAUSE = 'pause'
STATE_RESET = 'reset'
STATE_RESUME = 'resume'
STATE_SUSPEND = 'savestate'
STATE_POWER_OFF = 'poweroff'
STATE_SAVED = 'saved'

START_VM_GUI = 'gui'
START_VM_HEADLESS = 'headless'
START_VM_SDL = 'sdl'

STORAGE_DVD = 'dvddrive'
STORAGE_FDD = 'fdd'
STORAGE_HDD = 'hdd'

SYSTEM_BUS_IDE = 'ide'
SYSTEM_BUS_SATA = 'sata'
SYSTEM_BUS_SCSI = 'scsi'

VARIANT_ESX = 'ESX'
VARIANT_FIXED = 'Fixed'
VARIANT_STANDARD = 'Standard'
VARIANT_STREAM = 'Stream'
VARIANT_SPLIT2G = 'Split2G'

VHD_AUTO_RESET = 'auto_reset'
VHD_UUID = 'uuid'
VHD_PARENT_UUID = 'parrent_uuid'
VHD_CHILD_UUIDS = "child_uuids"
VHD_STATE = 'state'
VHD_TYPE = 'type'
VHD_PATH = 'path'
VHD_IMAGE_TYPE = 'disk_type'
VHD_VARIANT = 'variant'
VHD_CAPACITY = 'capacity'
VHD_SIZE_ON_DISK = 'size_on_disk'
VHD_USED_BY = 'usedby'

VHD_TYPE_NORMAL = 'normal'
VHD_TYPE_IMMUTABLE = 'immutable'
VHD_TYPE_READONLY = 'readonly'
VHD_TYPE_MULTIATTACH = 'multiattach'
VHD_TYPE_SHAREABLE = 'shareable'

VHD_STATE_INACCESSIBLE = 'inaccessible'
VHD_TYPE_ISCASI = 'iSCSI'

VRDE_SECURITY_CA = 'Security/CACertificate=%(path)s'
VRDE_SECURITY_SERVER_CERT = 'Security/ServerCertificate=%(path)s'
VRDE_SERCURITY_SERVER_PRIVATE_KEY = 'Security/ServerPrivateKey=%(path)s'
VRDE_SECURITY_METHOD = 'Security/Method=%(method)s'
# Note(alexandrucoman): The Security/Method VRDE property sets the desired
# security method, which is used for a connection. Valid values are:
# Negociate: the security method is negotiated with the client
# RDP: only Enhanced RDP Security is accepted. The client must support TLS.
# TLS: only Standard RDP Security is accepted.
VRDE_SECURITY_NEGOTIATE = 'Negotiate'
VRDE_SECURITY_RDP = 'RDP'
VRDE_SECURITY_TLS = 'TLS'

VBOX_VRDE_EXTPACK = 'vrdeextpack'
VBOX_MACHINE_FOLDER = 'machinefolder'

NS_ERROR_INVALID_ARG = 'NS_ERROR_INVALID_ARG'
NS_ERROR_FAILURE = 'NS_ERROR_FAILURE'
VBOX_E_ACCESSDENIED = 'E_ACCESSDENIED'
VBOX_E_FILE_ERROR = 'VBOX_E_FILE_ERROR'
VBOX_E_INVALID_OBJECT_STATE = 'VBOX_E_INVALID_OBJECT_STATE'
VBOX_E_INVALID_VM_STATE = 'VBOX_E_INVALID_VM_STATE'
VBOX_E_INVALID_VM_STATE_2 = 'Machine in invalid state'
VBOX_E_OBJECT_NOT_FOUND = 'VBOX_E_OBJECT_NOT_FOUND'
VERR_ACCESS_DENIED = 'VERR_ACCESS_DENIED'
VERR_ALREADY_EXISTS = 'VERR_ALREADY_EXISTS'
VERR_INTERNAL_ERROR = 'VERR_INTERNAL_ERROR'
VERR_NOT_SUPPORTED = 'VERR_NOT_SUPPORTED'
VBOX_E_INSTANCE_NOT_FOUND = 'Could not find a registered machine named'

VM_POWER_STATE = 'VMState'
VM_ACPI = 'acpi'
VM_CPUS = 'cpus'
VM_MEMORY = 'memory'
VM_VRDE_PORT = 'vrdeports'

POWER_STATE = {
    STATE_POWER_OFF: power_state.SHUTDOWN,
    'starting': power_state.RUNNING,
    'running': power_state.RUNNING,
    'paused': power_state.PAUSED,
    'aborted': power_state.SUSPENDED,
    STATE_SAVED: power_state.SUSPENDED,
}

SHOW_HD_INFO_KEYS = {
    'UUID': VHD_UUID,
    'Parent UUID': VHD_PARENT_UUID,
    'State': VHD_STATE,
    'Type': VHD_TYPE,
    'Location': VHD_PATH,
    'Storage format': VHD_IMAGE_TYPE,
    'Format variant': VHD_VARIANT,
    'Capacity': VHD_CAPACITY,
    'Size on disk': VHD_SIZE_ON_DISK,
    'In use by VMs': VHD_USED_BY,
    'Child UUIDs': VHD_CHILD_UUIDS,
    'Auto-Reset': VHD_AUTO_RESET,
}

ALL_ACPI_BUTTONS = (ACPI_POWER_BUTTON, ACPI_SLEEP_BUTTON)
ALL_DISK_FORMATS = (DISK_FORMAT_VDI, DISK_FORMAT_VHD, DISK_FORMAT_VMDK)
ALL_HD_FIELDS = (FIELD_HD_AUTORESET, FIELD_HD_COMPACT, FIELD_HD_RESIZE_BYTE,
                 FIELD_HD_RESIZE_MB, FIELD_HD_TYPE)
ALL_VHD_TYPES = (VHD_TYPE_SHAREABLE, VHD_TYPE_MULTIATTACH, VHD_TYPE_READONLY,
                 VHD_TYPE_IMMUTABLE, VHD_TYPE_NORMAL)
ALL_VM_FIELDS = (FIELD_CPUS, FIELD_DESCRIPTION, FIELD_MEMORY, FIELD_OS_TYPE)
ALL_VRDE_FIELDS = (FIELD_VRDE_EXTPACK, FIELD_VRDE_MULTICON, FIELD_VRDE_PORT,
                   FIELD_VRDE_PROPERTY, FIELD_VRDE_SERVER, FIELD_VRDE_VIDEO)
ALL_NETWORK_FIELDS = (FIELD_NIC, FIELD_NIC_TYPE, FIELD_CABLE_CONNECTED,
                      FIELD_BRIDGE_ADAPTER, FILED_MAC_ADDRESS)
ALL_STATES = (STATE_PAUSE, STATE_RESET, STATE_RESUME, STATE_SUSPEND,
              STATE_POWER_OFF)
ALL_STORAGES = (STORAGE_DVD, STORAGE_FDD, STORAGE_HDD)
ALL_START_VM = (START_VM_GUI, START_VM_HEADLESS, START_VM_SDL)
ALL_VARIANTS = (VARIANT_ESX, VARIANT_FIXED, VARIANT_STANDARD,
                VARIANT_STREAM, VARIANT_SPLIT2G)
ALL_VBOX_PROPERTIES = (VBOX_MACHINE_FOLDER, VBOX_VRDE_EXTPACK)

DEFAULT_IDE_CNAME = "IDE"
DEFAULT_SATA_CNAME = "SATA"
DEFAULT_SCSI_CNAME = "SCSI"

DEFAULT_IDE_CONTROLLER = CONTROLLER_PIIX4
DEFAULT_SATA_CONTROLLER = CONTROLLER_INTEL_AHCI
DEFAULT_SCSI_CONTROLLER = CONTROLLER_LSI_LOGIC

DEFAULT_DISK_FORMAT = DISK_FORMAT_VDI
DEFAULT_NIC_MODE = NIC_MODE_NULL
DEFAULT_NIC_TYPE = NIC_TYPE_AM79C973
DEFAULT_OS_TYPE = 'Other'
DEFAULT_PORTAL_PORT = 3260
DEFAULT_VARIANT = VARIANT_STANDARD
DEFAULT_ROOT_DEVICE = 'vda'
DEFAULT_ROOT_ATTACH_POINT = "%s-0-0" % SYSTEM_BUS_SATA.upper()
