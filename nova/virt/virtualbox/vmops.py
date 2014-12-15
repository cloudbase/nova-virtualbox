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
Management class for basic VM operations.
"""

import os

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import excutils
from oslo_utils import units

from nova import exception
from nova import i18n
from nova.virt import hardware
from nova.virt.virtualbox import constants
from nova.virt.virtualbox import exception as vbox_exc
from nova.virt.virtualbox import imagecache
from nova.virt.virtualbox import manage
from nova.virt.virtualbox import networkutils
from nova.virt.virtualbox import pathutils
from nova.virt.virtualbox import vhdutils
from nova.virt.virtualbox import vmutils
from nova.virt.virtualbox import volumeops
from nova.virt.virtualbox import volumeutils


CONF = cfg.CONF
CONF.import_opt('use_cow_images', 'nova.virt.driver')
LOG = logging.getLogger(__name__)


class VBoxOperation(object):

    """Management class for virtual machines operations."""

    def __init__(self):
        self._vbox_manage = manage.VBoxManage()
        self._volume = volumeops.VolumeOperations()

    def _inaccessible_vms(self):
        """Get the UUID for each virtual machine which is in inaccessible
        state.
        """
        list_vms = self._vbox_manage.list(constants.VMS_INFO)
        instance_list = []

        for virtual_machine in list_vms.splitlines():
            # Line format: "instance_name" {instance_uuid}
            try:
                name, uuid = virtual_machine.split()
            except ValueError:
                continue
            if name.strip('"') == "<inaccessible>":
                instance_list.append(uuid.strip(' {}'))

        return instance_list

    def init_host(self):
        """Initialize anything that is necessary for the driver to function,
        including catching up with currently running VM's on the given host.
        """

        # Update the Hypervisor internal database.
        # Remove all the inaccessible virtual hard disk which
        # not exist anymore.
        hdds = vhdutils.get_hard_disks()
        for uuid, disk in hdds.items():
            state = disk[constants.VHD_STATE]
            if not state == constants.VHD_STATE_INACCESSIBLE:
                continue

            # Check if the disk is still exists
            disk_file = disk.get(constants.VHD_PATH)
            if disk_file and not os.path.exists(disk_file):
                # Remove the disk from hypervisor
                LOG.info(i18n._LI("Remove inaccessible disk: %(disk)s"),
                         {"disk": disk})
                manage.VBoxManage.close_medium(constants.MEDIUM_DISK, uuid)

        # TODO(alexandrucoman): Check the inaccessible vms and try to
        # repair them.

    def _list_vms(self):
        """Process information from list vms.

        Return a dictionary which has `instance uuid` as key and
        `instance name` as value for all virtual machines currently
        registered with VirtualBox.
        """
        virtual_machines = {}
        list_vms = self._vbox_manage.list(constants.VMS_INFO)

        for virtual_machine in list_vms.splitlines():
            # Line format: "instance_name" {instance_uuid}
            try:
                name, uuid = virtual_machine.split()
            except ValueError:
                continue
            virtual_machines[name.strip('"')] = uuid.strip('{}')

        return virtual_machines

    def list_instances(self):
        """Return the names of all the instances known to the virtualization
        layer, as a list.
        """
        return self._list_vms().keys()

    def list_instance_uuids(self):
        """Return the UUIDS of all the instances known to the virtualization
        layer, as a list.
        """
        return self._list_vms().values()

    def instance_exists(self, instance):
        """Check existence of an instance on the host."""
        list_vms = self._vbox_manage.list(constants.VMS_INFO)

        for virtual_machine in list_vms.splitlines():
            # Line format: "instance_name" {instance_uuid}
            try:
                vm_name, _ = virtual_machine.split()
            except ValueError:
                continue

            if instance.name == vm_name.strip(' "'):
                return True

        return False

    def get_info(self, instance):
        """Get the current status of an instance, by name."""
        vm_info = self._vbox_manage.show_vm_info(instance)

        state = vm_info.get(constants.VM_POWER_STATE)
        cpu_count = vm_info.get(constants.VM_CPUS, 0)
        memory = vm_info.get(constants.VM_MEMORY, 0)

        state = constants.POWER_STATE.get(state, 0)
        return hardware.InstanceInfo(state=state,
                                     max_mem_kb=memory,
                                     mem_kb=memory,
                                     num_cpu=cpu_count,
                                     cpu_time_ns=0)

    def pause(self, instance):
        """Put a virtual machine on hold, without changing its state
        for good.
        """
        LOG.debug("Pause instance", instance=instance)
        self._vbox_manage.control_vm(instance, constants.STATE_PAUSE)

    def unpause(self, instance):
        """Undo a previous pause command."""
        LOG.debug("Unpause instance", instance=instance)
        self._vbox_manage.control_vm(instance, constants.STATE_RESUME)

    def suspend(self, instance):
        """Save the current state of the virtual machine to disk and
        then stop the virtual machine.
        """
        LOG.debug("Suspend instance", instance=instance)
        self._vbox_manage.control_vm(instance, constants.STATE_SUSPEND)

    def resume(self, instance, context=None, network_info=None,
               block_device_info=None):
        """Resume the specified instance.

        :param context: the context for the resume
        :param instance: nova.objects.instance.Instance being resumed
        :param network_info:
           :py:meth:`~nova.network.manager.NetworkManager.get_instance_nw_info`
        :param block_device_info: instance volume block device info
        """
        # TODO(alexandrucoman): Process the information from the unused
        #                       arguments.
        self._vbox_manage.start_vm(instance)

    def power_off(self, instance, timeout=0, retry_interval=0):
        """Power off has the same effect on a virtual machine as
        pulling the power cable on a real computer.

        .. note::
            If timeout is greater than 0 it will try to power off
            virtual machine softly.

            The state of the VM is not saved beforehand, and data
            may be lost.
        """
        LOG.debug("Power off instance %(instance)s",
                  {"instance": instance.name})
        try:
            if timeout and vmutils.soft_shutdown(instance, timeout,
                                                 retry_interval):
                LOG.info(i18n._LI("Soft shutdown succeeded."),
                         instance=instance)
                return
        except (vbox_exc.VBoxException, exception.InstanceInvalidState) as exc:
            LOG.debug("Soft shutdown failed: %(instance)s: %(error)s",
                      {"error": exc, "instance": instance.name})

        self._vbox_manage.control_vm(instance, constants.STATE_POWER_OFF)

    def power_on(self, instance, context=None, network_info=None,
                 block_device_info=None):
        """Power on the specified instance.

        :param instance: nova.objects.instance.Instance
        """
        # TODO(alexandrucoman): Process the information from the unused
        #                       arguments.
        self._vbox_manage.start_vm(instance)

    def reboot(self, instance, context=None, network_info=None,
               reboot_type=None, block_device_info=None,
               bad_volumes_callback=None):
        """Reboot the specified instance.

        After this is called successfully, the instance's state
        goes back to power_state.RUNNING. The virtualization
        platform should ensure that the reboot action has completed
        successfully even in cases in which the underlying domain/vm
        is paused or halted/stopped.
        """
        # TODO(alexandrucoman): Process the information from the unused
        #                       arguments.
        if reboot_type == constants.REBOOT_SOFT:
            if vmutils.soft_shutdown(instance):
                self.power_on(instance)
                return

        self._vbox_manage.control_vm(instance, constants.STATE_RESET)

    def _network_setup(self, instance, network_info):
        nic_info = {}
        for vif in network_info:
            LOG.debug('Creating nic for instance', instance=instance)
            networkutils.create_nic(instance, vif)
            nic_info[networkutils.mac_address(vif['address'])] = vif['id']
        vmutils.update_description(instance, {"network": nic_info})

    def create_ephemeral_disk(self, instance):
        eph_vhd_size = instance.get('ephemeral_gb', 0) * units.Gi
        if not eph_vhd_size:
            return

        eph_vhd_format = constants.DEFAULT_DISK_FORMAT
        eph_vhd_path = pathutils.ephemeral_vhd_path(instance, eph_vhd_format)
        self._vbox_manage.create_hd(filename=eph_vhd_path,
                                    size=eph_vhd_size / units.Mi,
                                    disk_format=eph_vhd_format,
                                    variant=constants.VARIANT_STANDARD)
        self._vbox_manage.modify_hd(filename=eph_vhd_path,
                                    field=constants.FIELD_HD_TYPE,
                                    value=constants.VHD_TYPE_IMMUTABLE)

        # Note(alexandrucoman): For immutable (differencing) hard disks only
        # Autoreset option determines whether the disk is automatically reset
        # on every VM startup
        # self._vbox_manage.modify_hd(filename=eph_vhd_path,
        #                             field=constants.FIELD_HD_AUTORESET,
        #                             value=constants.ON)
        return eph_vhd_path

    def create_root_disk(self, context, instance):
        base_vhd_path = imagecache.get_cached_image(context, instance)
        base_info = vhdutils.disk_info(base_vhd_path)
        root_vhd_path = pathutils.root_disk_path(
            instance, disk_format=base_info[constants.VHD_IMAGE_TYPE])

        if CONF.use_cow_images:
            LOG.debug("Creating differencing VHD. Parent: %(parent)s, "
                      "Target: %(target)s", {'parent': base_vhd_path,
                                             'target': root_vhd_path},
                      instance=instance)
            self._vbox_manage.create_hd(
                filename=root_vhd_path,
                # disk_format=base_info[constants.VHD_IMAGE_TYPE],
                variant=constants.VARIANT_STANDARD,
                parent=base_vhd_path
            )

        else:
            LOG.debug("Cloning VHD image %(base)s to target: %(target)s",
                      {'base': base_vhd_path, 'target': root_vhd_path},
                      instance=instance)
            self._vbox_manage.clone_hd(
                vhd_path=base_vhd_path,
                new_vdh_path=root_vhd_path,
                disk_format=base_info[constants.VHD_IMAGE_TYPE],
                variant=constants.VARIANT_STANDARD
            )

        # Resize image if is necesary
        disk_format = vhdutils.get_image_type(root_vhd_path)
        if instance.root_gb and disk_format in (constants.DISK_FORMAT_VDI,
                                                constants.DISK_FORMAT_VHD):
            base_vhd_size = base_info[constants.VHD_CAPACITY] / units.Mi
            root_vhd_size = instance.root_gb * units.Ki
            if vhdutils.is_resize_required(disk_path=root_vhd_path,
                                           old_size=base_vhd_size,
                                           new_size=root_vhd_size,
                                           instance=instance):
                self._vbox_manage.modify_hd(
                    root_vhd_path, constants.FIELD_HD_RESIZE_MB, root_vhd_size)

        return root_vhd_path

    def create_instance(self, instance, image_meta, network_info,
                        overwrite=True):
        image_properties = image_meta.get("properties", {})
        action = constants.PATH_DELETE if overwrite else None

        basepath = pathutils.instance_basepath(instance, action=action)
        self._vbox_manage.create_vm(
            instance.name, basefolder=os.path.dirname(basepath),
            register=True)

        vmutils.set_os_type(instance, image_properties.get('os_type', None))
        vmutils.set_memory(instance)
        vmutils.set_cpus(instance)
        self._network_setup(instance, network_info)

    def storage_setup(self, instance, root_path, ephemeral_path,
                      block_device_info):
        for system_bus in (constants.SYSTEM_BUS_SATA,
                           constants.SYSTEM_BUS_SCSI):
            vmutils.set_storage_controller(instance, system_bus)

        port = 0
        for disk_path in (root_path, ephemeral_path):
            if disk_path:
                self._volume.attach_storage(
                    instance=instance, port=port, device=0,
                    controller=constants.SYSTEM_BUS_SATA.upper(),
                    drive_type=constants.STORAGE_HDD, medium=disk_path
                )
                port = port + 1

        self._volume.attach_volumes(instance, block_device_info,
                                    ebs_root=root_path is None)

    def destroy(self, instance, context=None, network_info=None,
                block_device_info=None, destroy_disks=True,
                migrate_data=None):
        """Destroy the specified instance from the Hypervisor."""
        LOG.info(i18n._("Got request to destroy instance"), instance=instance)
        if not self.instance_exists(instance):
            LOG.warning(i18n._("Instance do not exists."), instance=instance)
            return

        power_state = vmutils.get_power_state(instance)
        if power_state not in (constants.STATE_POWER_OFF,
                               constants.STATE_SAVED):
            self._vbox_manage.control_vm(instance, constants.STATE_POWER_OFF)

        try:
            self._vbox_manage.unregister_vm(instance, delete=destroy_disks)
            if destroy_disks:
                pathutils.instance_basepath(
                    instance, action=constants.PATH_DELETE)
        except vbox_exc.VBoxException:
            with excutils.save_and_reraise_exception():
                LOG.exception(i18n._('Failed to destroy instance: %s'),
                              instance.name)

    def spawn(self, context, instance, image_meta, injected_files,
              admin_password, network_info, block_device_info):
        """Create a new VM on the virtualization platform.

        Once this successfully completes, the instance should be
        running (power_state.RUNNING).
        """
        LOG.info(i18n._("Got request to spawn instance"), instance=instance)
        if self.instance_exists(instance):
            raise exception.InstanceExists(name=instance.name)

        try:
            self.create_instance(instance, image_meta, network_info)

            root_path = None
            if not volumeutils.ebs_root_in_block_devices(block_device_info):
                root_path = self.create_root_disk(context, instance)
            ephemeral_path = self.create_ephemeral_disk(instance)

            self.storage_setup(instance, root_path, ephemeral_path,
                               block_device_info)
            # TODO(alexandrucoman): Create the config drive
        except vbox_exc.VBoxException:
            with excutils.save_and_reraise_exception():
                self.destroy(instance)

        LOG.info(i18n._("The instance was successfully spawned!"),
                 instance=instance)
