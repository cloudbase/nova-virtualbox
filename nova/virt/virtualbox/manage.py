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
A connection to VirtualBox via VBoxManage.
"""

import os
import time

from oslo_config import cfg
from oslo_concurrency import processutils
from oslo_log import log as logging

from nova import exception
from nova.i18n import _LW
from nova import utils
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exc

LOG = logging.getLogger(__name__)
VIRTUAL_BOX = [
    cfg.IntOpt('retry_count',
               default=3,
               help='The number of times to retry to execute command.'),
    cfg.IntOpt('retry_interval',
               default=1,
               help='Interval between execute attempts, in seconds.'),
    cfg.StrOpt('vboxmanage_cmd',
               default="VBoxManage",
               help='Path of VBoxManage executable which is used to '
                    'comunicate with the VirtualBox.'),
]

CONF = cfg.CONF
CONF.register_opts(VIRTUAL_BOX, 'virtualbox')


class VBoxManage(object):

    # Commands list
    CONTROL_VM = "controlvm"
    CLONE_HD = "clonehd"
    CLOSE_MEDIUM = "closemedium"
    CREATE_HD = "createhd"
    CREATE_VM = "createvm"
    LIST = "list"
    MODIFY_HD = "modifyhd"
    MODIFY_VM = "modifyvm"
    SET_PROPERTY = "setproperty"
    SHOW_VM_INFO = "showvminfo"
    SHOW_HD_INFO = "showhdinfo"
    SNAPSHOT = "snapshot"
    START_VM = "startvm"
    STORAGE_ATTACH = "storageattach"
    STORAGE_CTL = "storagectl"
    UNREGISTER_VM = "unregistervm"
    VERSION = "--version"

    @classmethod
    def _execute(cls, command, *args):
        """Execute the received command and returns stdout and stderr."""
        LOG.debug("Execute: VBoxManage --nologo %(command)s %(args)s",
                  {"command": command, "args": args})

        for _ in range(CONF.virtualbox.retry_count):
            try:
                stdout, stderr = utils.execute(
                    CONF.virtualbox.vboxmanage_cmd, "--nologo",
                    command.lower(), *args)
            except processutils.ProcessExecutionError as exc:
                stdout, stderr = exc.stdout, exc.stderr

            if (constants.VBOX_E_ACCESSDENIED in stderr or
                    constants.VBOX_E_INVALID_OBJECT_STATE in stderr):
                LOG.warning(_LW("Something went wrong, trying again."))
                time.sleep(CONF.virtualbox.retry_interval)
                continue

            break
        else:
            LOG.warning(_LW("Failed to process command."))

        return (stdout, stderr)

    @classmethod
    def _check_stderr(cls, stderr, instance=None, method=None):
        # TODO(alexandrucoman): Check for another common exceptions
        if constants.VBOX_E_INSTANCE_NOT_FOUND in stderr:
            raise exception.InstanceNotFound(instance_id=instance.uuid)

        if (constants.VBOX_E_INVALID_VM_STATE in stderr or
                constants.VBOX_E_INVALID_VM_STATE_2 in stderr):
            raise exception.InstanceInvalidState(
                attr=None, instance_uuid=instance.uuid,
                state=instance.power_state, method=method)

    @classmethod
    def _storageattach(cls, instance, controller, port, device, drive_type,
                       medium, *args):
        """Attach, modify or remove a storage medium connected to a
        storage controller.
        """
        command = [cls.STORAGE_ATTACH, instance.name,
                   "--storagectl", controller,
                   "--port", port,
                   "--device", device,
                   "--type", drive_type,
                   "--medium", medium]
        if args:
            command.extend(args)

        output, error = cls._execute(*command)
        if error:
            if constants.NS_ERROR_INVALID_ARG in error:
                raise vbox_exc.VBoxInvalid(reason=error)
            cls._check_stderr(error, instance, cls.STORAGE_ATTACH)

        return (output, error)

    @classmethod
    def version(cls):
        """Return the VirtualBox version."""
        output, _ = cls._execute(cls.VERSION)
        return output

    @classmethod
    def set_property(cls, name, value):
        """Change global settings which affect the entire VirtualBox
        installation.

        For property name the following values are allowed:
            'VBOX_VRDE_EXTPACK':    This specifies which library implements the
                                    VirtualBox Remote Desktop Extension.
            'VBOX_MACHINE_FOLDER':  This specifies the default folder in
                                    which virtual machine definitions are kept.
        """
        if name not in constants.ALL_VBOX_PROPERTIES:
            raise vbox_exc.VBoxValueNotAllowed(
                argument="name", value=name, method=cls.SET_PROPERTY,
                allowed_values=constants.ALL_VBOX_PROPERTIES)

        _, error = cls._execute(cls.SET_PROPERTY, name, value)
        if error:
            raise vbox_exc.VBoxManageError(method=cls.SET_PROPERTY,
                                           reason=error)

    @classmethod
    def control_vm(cls, instance, state):
        """Change the state of a virtual machine that is currently
        running.

        :param instance: nova.objects.instance.Instance
        :param state: one of the state from ALL_STATES container or
                      one button from ALL_ACPI_BUTTONS
        """
        valid_states = constants.ALL_STATES + constants.ALL_ACPI_BUTTONS
        if state not in valid_states:
            # Unknown state for VirtualBox
            raise vbox_exc.VBoxValueNotAllowed(
                argument="state", value=state, method=cls.CONTROL_VM,
                allowed_values=valid_states)

        _, error = cls._execute(cls.CONTROL_VM, instance.name, state)

        if error and constants.DONE not in error:
            cls._check_stderr(error, instance, cls.CONTROL_VM)
            raise vbox_exc.VBoxManageError(method=cls.CONTROL_VM,
                                           reason=error)

    @classmethod
    def start_vm(cls, instance, method=constants.START_VM_HEADLESS):
        """Start a virtual machine that is currently in the
        "Powered off" or "Saved" states.

        For method the following values are allowed:
            :START_VM_GUI:      Starts a virtual machine showing a GUI
                                window.
            :START_VM_HEADLESS: Starts a virtual machine without a
                                window for remote display only.
            :START_VM_SDL:      Starts a virtual machine with a minimal
                                GUI and limited features.
        """
        if method not in constants.ALL_START_VM:
            raise vbox_exc.VBoxValueNotAllowed(
                argument="method", value=method, method=cls.START_VM,
                allowed_values=constants.ALL_START_VM)

        for _ in range(CONF.virtualbox.retry_count):
            output, error = cls._execute(cls.START_VM, instance.name, "--type",
                                         method)
            if error and constants.DONE not in error:
                if constants.VERR_INTERNAL_ERROR in error:
                    LOG.warning(_LW("Something went wrong, trying again."))
                    time.sleep(CONF.virtualbox.retry_interval)
                    continue
                cls._check_stderr(error, instance, cls.START_VM)
                raise vbox_exc.VBoxManageError(method="startvm", reason=error)
            break

    @classmethod
    def modify_hd(cls, filename, field, value=None):
        """Change the characteristics of a disk image after it has
        been created.

        The following fields are available with VBoxManage modifyhd:
            :FIELD_HD_AUTORESET:    determines whether the disk is
                                    automatically reset on every VM startup
            :FIELD_HD_COMPACT:      compact disk images, i.e. remove blocks
                                    that only contains zeroes
            :FIELD_HD_RESIZE_BYTE:  allows you to change the capacity of
                                    an existing image
            :FIELD_HD_RESIZE_MB:    allows you to change the capacity of
                                    an existing image
        """
        if field not in constants.ALL_HD_FIELDS:
            raise vbox_exc.VBoxValueNotAllowed(
                argument="field", value=field, method=cls.MODIFY_HD,
                allowed_values=constants.ALL_START_VM)

        command = [cls.MODIFY_HD, filename, field]
        if value:
            command.append(value)

        _, error = cls._execute(*command)
        if error and constants.DONE not in error:
            raise vbox_exc.VBoxManageError(method=cls.MODIFY_HD, reason=error)

    @classmethod
    def modify_vm(cls, instance, field, *args):
        """Change general settings for a registered virtual machine.

        The following fields are available with VBoxManage modifyvm:
            :FIELD_OS_TYPE: This specifies what guest operating system
                            is supposed to run in the virtual machine
            :FIELD_MEMORY:  This sets the amount of RAM, in MB, that
                            the virtual machine should allocate for
                            itself from the host
            :FIELD_CPUS:    This sets the number of virtual CPUs for the
                            virtual machine

        .. note::
            Is required that the machine to be powered off (either
            running or in "saved" state).
        """
        if field not in constants.ALL_VM_FIELDS:
            raise vbox_exc.VBoxValueNotAllowed(
                argument="field", value=field, method=cls.MODIFY_VM,
                allowed_values=constants.ALL_VM_FIELDS)

        _, error = cls._execute(cls.MODIFY_VM, instance.name, field, *args)
        if error:
            cls._check_stderr(error, instance, cls.MODIFY_VM)
            raise vbox_exc.VBoxManageError(method=cls.MODIFY_VM, reason=error)

    @classmethod
    def modify_network(cls, instance, field, index, value):
        """Change the network settings for a registered virtual machine.

        :param instance:
        :param field:
        :param index: specifies the virtual network adapter whose
                      settings should be changed.
        :param value:

        The following fields are available with VBoxManage modify_network:
            :FIELD_NIC:             type of networking (nat, bridge etc)
            :FIELD_NIC_TYPE:        networking hardware
            :FIELD_CABLE_CONNECTED: connect / disconnect network
            :FIELD_BRIDGE_ADAPTER:  host interface used by virtual network
                                    interface
            :FILED_MAC_ADDRESS:     MAC address of the virtual network card
        """
        if field not in constants.ALL_NETWORK_FIELDS:
            raise vbox_exc.VBoxValueNotAllowed(
                argument="field", value=field, method="modify_network",
                allowed_values=constants.ALL_NETWORK_FIELDS)

        _, error = cls._execute(cls.MODIFY_VM, instance.name,
                                field % {"index": index}, value)
        if error:
            cls._check_stderr(error, instance, "modify_network")
            raise vbox_exc.VBoxManageError(method="modify_network",
                                           reason=error)

    @classmethod
    def modify_vrde(cls, instance, field, value):
        """Change settings regarding VRDE for a registered virtual machine.

        The following fields are available with VBoxManage modify_vrde:
            :FIELD_VRDE_EXTPACK:    specifies which VRDE library will be used
            :FIELD_VRDE_MULTICON:   enables multiple connections to the same
                                    VRDE server
            :FIELD_VRDE_PORT:       a port or a range of ports the VRDE server
                                    can bind to
            :FIELD_VRDE_SERVER:     enables or disables the VirtualBox remote
                                    desktop extension (VRDE) server
            :FIELD_VRDE_VIDEO:      enables or disables video redirection,
                                    if it is supported by the VRDE server
        """
        if field not in constants.ALL_VRDE_FIELDS:
            raise vbox_exc.VBoxValueNotAllowed(
                argument="field", value=field, method="modify_vrde",
                allowed_values=constants.ALL_VRDE_FIELDS)

        _, error = cls._execute(cls.MODIFY_VM, instance.name, field, value)
        if error:
            cls._check_stderr(error, instance, "modify_vrde")
            raise vbox_exc.VBoxManageError(method="modify_vrde",
                                           reason=error)

    @classmethod
    def list(cls, information):
        """Gives relevant information about host and information
        about VirtualBox's current settings.

        The following information are available with VBoxManage list:
            :HOST_INFO:         information about the host system
            :OSTYPES_INFO:      lists all guest operating systems
                                presently known to VirtualBox
            :VMS_INFO:          lists all virtual machines currently
                                registered with VirtualBox
            :RUNNINGVMS_INFO:   lists all currently running virtual
                                machines by their unique identifiers
        """
        output, error = cls._execute(cls.LIST, information)
        if error:
            raise vbox_exc.VBoxManageError(method=cls.LIST, reason=error)
        return output

    @classmethod
    def show_vm_info(cls, instance):
        """Show the configuration of a particular VM."""
        information = {}
        output, error = cls._execute(cls.SHOW_VM_INFO, instance.name,
                                     "--machinereadable")
        if error:
            cls._check_stderr(error, instance, cls.SHOW_VM_INFO)
            raise vbox_exc.VBoxManageError(method=cls.SHOW_VM_INFO,
                                           reason=error)

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            key, separator, value = line.partition("=")
            value = value.strip(' "')
            key = key.strip(' "')
            if separator != "=":
                LOG.warning("Could not parse the following line: %s", line)
                continue

            information[key] = value if value != "none" else None

        return information

    @classmethod
    def show_hd_info(cls, vhd):
        """Shows information about a virtual hard disk image."""
        output, error = cls._execute(cls.SHOW_HD_INFO, vhd)

        if error:
            if constants.NS_ERROR_INVALID_ARG in error:
                raise vbox_exc.VBoxInvalid(reason=error)

            raise vbox_exc.VBoxManageError(method=cls.SHOW_HD_INFO,
                                           reason=error)
        return output

    @classmethod
    def create_hd(cls, filename, size=None,
                  disk_format=constants.DISK_FORMAT_VDI,
                  variant=constants.VARIANT_STANDARD, parent=None):
        """Creates a new virtual hard disk image.

        :param filename:    the file name for the hard disk image
        :param size:        the image capacity, in MiB units
        :param disk_format: file format for the output file
                            (default: DISK_FORMAT_VDI)
        :param variant:     file format variant for the output file
                            (default: VARIANT_STANDARD)
        :param parent:
        :return:            UUID for the disk image created
        """

        if disk_format not in constants.ALL_DISK_FORMATS:
            raise exception.InvalidDiskFormat(disk_format=disk_format)

        if variant not in constants.ALL_VARIANTS:
            raise vbox_exc.VBoxValueNotAllowed(
                argument="variant", value=variant, method=cls.CREATE_HD,
                allowed_values=constants.ALL_VARIANTS)

        if size and size < 1:
            raise exception.InvalidDiskInfo(
                reason="Disk size should be bigger than 0.")

        command = [cls.CREATE_HD,
                   "--filename", filename,
                   "--format", disk_format,
                   "--variant", variant]
        if size:
            command.extend(["--size", size])

        if parent:
            command.extend(["--diffparent", parent])

        output, error = cls._execute(*command)

        if error and constants.DONE not in error:
            if constants.VBOX_E_FILE_ERROR in error:
                raise exception.DestinationDiskExists(path=filename)
            raise vbox_exc.VBoxManageError(method=cls.CREATE_HD, reason=error)

        # The ouput should look like:
        # Disk image created. UUID: 6917a94b-ecb0-4996-8ab8-5e4ef8f9539a
        for line in output.splitlines():
            if "UUID:" not in line:
                continue
            hd_uuid = line.split("UUID:")[1].strip()
            break
        else:
            # TODO(alexandrucoman): Fail to get UUID (Something went wrong)
            return

        return hd_uuid

    @classmethod
    def clone_hd(cls, vhd_path, new_vdh_path, disk_format=None, variant=None,
                 existing=False):
        """Duplicate a registered virtual hard disk image to a new image
        file with a new unique identifier.

        :param vhd_path:        path for the input virtual hard drive
        :param new_vdh_path:    path for the output virtual hard drive
        :param disk_format:     file format for the output file
                                (default: DISK_FORMAT_VDI)
        :param variant:         file format variant for the output file
                                (default: VARIANT_STANDARD)
        :param existing:        perform the clone operation to an already
                                existing destination medium.
        """
        command = [cls.CLONE_HD, vhd_path, new_vdh_path]
        if disk_format:
            command.extend(["--format", disk_format])

        if variant:
            command.extend(["--variant", variant])

        if existing:
            command.append("--existing")

        _, error = cls._execute(*command)
        if error and constants.DONE not in error:
            if constants.VBOX_E_FILE_ERROR in error:
                LOG.debug("Fail to clone hd: %(error)s", {"error": error})
                raise exception.DestinationDiskExists(path=new_vdh_path)

            raise vbox_exc.VBoxManageError(method=cls.CLONE_HD, reason=error)

    @classmethod
    def create_vm(cls, name, basefolder=None, register=False):
        """Creates a new XML virtual machine definition file.

        :param name:          the name of the virtual machine
        :param basefolder:    the path for virtual machine
        :param register:      import a virtual machine definition in
                              an XML file into VirtualBox
        :type register:       bool

        :return:              UUID for the disk image created

        .. note::

            If the basefolder is provided, the machine folder will be
            named with :param basefolder: dirname. In this case, the
            names of the file and the folder will not change if the
            virtual machine is renamed.
        """
        command = [cls.CREATE_VM, "--name", name]
        if basefolder:
            command.extend(["--basefolder", basefolder])

        if register:
            command.extend(["--register"])

        output, error = cls._execute(*command)
        if error:
            if constants.VBOX_E_FILE_ERROR in error:
                path = name if not basefolder else os.path.join(basefolder,
                                                                name)
                raise exception.DestinationDiskExists(path=path)

            raise vbox_exc.VBoxManageError(method=cls.CREATE_VM, reason=error)

        for line in output.splitlines():
            if "UUID:" not in line:
                continue
            vm_uuid = line.split("UUID:")[1].strip()
            break
        else:
            # TODO(alexandrucoman): Fail to get UUID (Something went wrong)
            return

        return vm_uuid

    @classmethod
    def storage_ctl(cls, instance, name, system_bus, controller):
        """Attach or modify a storage controller.

        :param instance:    nova.objects.instance.Instance
        :param name:        name of the storage controller.
        :param system_bus:  type of the system bus to which the storage
                            controller must be connected.
        :param controller:  type of chipset being emulated for the given
                            storage controller.
        """
        _, error = cls._execute(cls.STORAGE_CTL, instance.name,
                                "--name", name,
                                "--add", system_bus,
                                "--controller", controller)
        if error:
            # TODO(alexandrucoman): Check for specific error code
            #                       like constants.NS_ERROR_INVALID_ARG
            raise vbox_exc.VBoxManageError(method=cls.STORAGE_CTL,
                                           reason=error)

    @classmethod
    def storage_attach(cls, instance, controller, port, device, drive_type,
                       medium):
        """Attach, modify or remove a storage medium connected to a
        storage controller.

        :param controller:  name of the storage controller.
        :param port:        the number of the storage controller's port
                            which is to be modified.
        :param device:      the number of the port's device which is to
                            be modified.
        :param drive_type:  define the type of the drive to which the
                            medium is being attached.
        :param medium:      specifies what is to be attached
        """
        if drive_type not in constants.ALL_STORAGES:
            raise vbox_exc.VBoxValueNotAllowed(
                argument="drive_type", value=drive_type,
                method="storage_attach",
                allowed_values=constants.ALL_STORAGES)

        _, error = cls._storageattach(instance, controller, port, device,
                                      drive_type, medium)
        if error:
            raise vbox_exc.VBoxManageError(method="storageattach",
                                           reason=error)

    @classmethod
    def scsi_storage_attach(cls, instance, controller, port, device,
                            connection_info, initiator):
        """Attach a storage medium using ISCSI.

        :param controller:      name of the storage controller.
        :param port:            the number of the storage controller's port
                                which is to be modified.
        :param device:          the number of the port's device which is to
                                be modified.
        :param connection_info: information regarding the iSCSI portal and
                                volume
        """
        data = connection_info['data']
        auth_username = data.get('auth_username')
        auth_password = data.get('auth_password')
        try:
            portal_ip, portal_port = data['target_portal'].split(':')
        except ValueError:
            portal_ip = data['target_portal']
            portal_port = constants.DEFAULT_PORTAL_PORT

        information = [constants.FIELD_PORTAL, portal_ip,
                       constants.FIELD_PORTAL_PORT, portal_port,
                       constants.FIELD_LUN, data['target_lun'],
                       constants.FIELD_TARGET, data['target_iqn'],
                       constants.FIELD_INITIATOR, initiator]

        if auth_password and auth_username:
            information.extend([constants.FIELD_USERNAME, auth_username,
                                constants.FIELD_PASSWORD, auth_password])

        _, error = cls._storageattach(instance, controller, port, device,
                                      constants.STORAGE_HDD,
                                      constants.MEDIUM_ISCSI,
                                      *information)
        if error:
            raise vbox_exc.VBoxManageError(method="storageattach",
                                           reason=error)

    @classmethod
    def unregister_vm(cls, instance, delete=True):
        """Unregister a virtual machine.

        If delete is True, the following files will automatically
        be deleted as well:
            * all hard disk image files, including differencing files,
            which are used by the machine and not shared with other machines;
            * saved state files that the machine created
            * the machine XML file and its backups;
            * the machine log files;
            * the machine directory, if it is empty after having deleted
              all the above;
        """
        command = [cls.UNREGISTER_VM, instance.name]
        if delete:
            command.append('--delete')

        _, error = cls._execute(*command)
        if error and constants.DONE not in error:
            cls._check_stderr(error, instance, cls.UNREGISTER_VM)
            raise vbox_exc.VBoxManageError(method=cls.UNREGISTER_VM,
                                           reason=error)

    @classmethod
    def take_snapshot(cls, instance, name, description=None, live=None):
        """Take a snapshot of the current state of the virtual machine.
        :param instance:        nova.objects.instance.Instance
        :param name:            (str) snapshot name
        :param description:     (str) snapshot description
        :param live:            (bool)

        .. note::
            If live is specified, the VM will not be stopped during
            the snapshot creation (live smapshotting).
        """

        command = [cls.SNAPSHOT, instance.name, 'take', name]
        if description:
            command.extend(['--description', description])

        if live:
            command.append('--live')

        _, error = cls._execute(*command)
        if error and constants.DONE not in error:
            raise vbox_exc.VBoxManageError(method="snapshot", reason=error)

    @classmethod
    def delete_snapshot(cls, instance, name):
        """Delete a snapshot (specified by name or by UUID).

        .. note::
            This can take a while to finish since the differencing images
            associated with the snapshot might need to be merged with their
            child differencing images.
        """
        _, error = cls._execute(cls.SNAPSHOT, instance.name, 'delete', name)
        if error and constants.DONE not in error:
            raise vbox_exc.VBoxManageError(method="snapshot", reason=error)

    @classmethod
    def set_vhd_uuid(cls, disk):
        """Assign a new UUID to the given image file.

        This way, multiple copies of a container can be registered.
        """
        _, error = cls._execute('internalcommands', 'sethduuid', disk)
        if error:
            raise vbox_exc.VBoxManageError(method="sethduuid",
                                           reason=error)

    @classmethod
    def set_disk_parent_uuid(cls, disk_file, parent_uuid):
        """Assigns a new parent UUID to the given image file."""
        _, error = cls._execute('internalcommands', 'sethdparentuuid',
                                disk_file, parent_uuid)
        if error:
            raise vbox_exc.VBoxManageError(method="sethdparentuuid",
                                           reason=error)

    @classmethod
    def close_medium(cls, medium, path, delete=False):
        """Remove a medium from a VirtualBox media registry."""
        command = [cls.CLOSE_MEDIUM, medium, path]
        if delete:
            command.append("--delete")
        _, error = cls._execute(*command)
        if error and constants.DONE not in error:
            raise vbox_exc.VBoxManageError(method=cls.CLOSE_MEDIUM,
                                           reason=error)
