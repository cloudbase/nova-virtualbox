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
A connection to the VirtualBox
"""
import platform

from nova.virt import driver
from nova.virt.virtualbox import consoleops
from nova.virt.virtualbox import hostops
from nova.virt.virtualbox import migrationops
from nova.virt.virtualbox import snapshotops
from nova.virt.virtualbox import vmops
from nova.virt.virtualbox import volumeops


class VirtualBoxDriver(driver.ComputeDriver):

    def __init__(self, virtapi):
        super(VirtualBoxDriver, self).__init__(virtapi)
        self._console_ops = consoleops.ConsoleOps()
        self._migrationops = migrationops.MigrationOperations()
        self._vbox_ops = vmops.VBoxOperation()
        self._snapshot_ops = snapshotops.SnapshotOperations()
        self._volume_ops = volumeops.VolumeOperations()

    def init_host(self, host):
        """Initialize anything that is necessary for the driver to function,
        including catching up with currently running VM's on the given host.
        """
        self._console_ops.setup_host()
        self._vbox_ops.init_host()

    def get_available_resource(self, nodename):
        """Retrieve resource information.

        This method is called when nova-compute launches, and
        as part of a periodic task that records the results in the DB.

        :param nodename:
            node which the caller want to get resources from
            a driver that manages only one node can safely ignore this
        :returns: Dictionary describing resources
        """
        return hostops.get_available_resource()

    def get_available_nodes(self, refresh=False):
        """Returns nodenames of all nodes managed by the compute service.

        This method is for multi compute-nodes support. If a driver supports
        multi compute-nodes, this method returns a list of nodenames managed
        by the service. Otherwise, this method should return
        [hypervisor_hostname].
        """
        return [platform.node()]

    def list_instances(self):
        """Return the names of all the instances known to the virtualization
        layer, as a list.
        """
        return self._vbox_ops.list_instances()

    def list_instance_uuids(self):
        """Return the UUIDS of all the instances known to the virtualization
        layer, as a list.
        """
        return self._vbox_ops.list_instance_uuids()

    def instance_exists(self, instance):
        """Checks existence of an instance on the host.

        :param instance: The instance to lookup

        Returns True if an instance with the supplied ID exists on
        the host, False otherwise.
        """
        return self._vbox_ops.instance_exists(instance)

    def get_info(self, instance):
        """Get the current status of an instance, by name.

        Returns a dict containing:

        :state:         the running state, one of the power_state codes
        :max_mem:       (int) the maximum memory in KBytes allowed
        :mem:           (int) the memory in KBytes used by the domain
        :num_cpu:       (int) the number of virtual CPUs for the domain
        :cpu_time:      (int) the CPU time used in nanoseconds
        """
        return self._vbox_ops.get_info(instance)

    def spawn(self, context, instance, image_meta, injected_files,
              admin_password, network_info=None, block_device_info=None,
              flavor=None):
        """Create a new instance/VM/domain on the virtualization platform.

        Once this successfully completes, the instance should be
        running (power_state.RUNNING).

        If this fails, any partial instance should be completely
        cleaned up, and the virtualization platform should be in the state
        that it was before this call began.

        :param context: security context
        :param instance: nova.objects.instance.Instance
                         This function should use the data there to guide
                         the creation of the new instance.
        :param image_meta: image object returned by nova.image.glance that
                           defines the image from which to boot this instance
        :param injected_files: User files to inject into instance.
        :param admin_password: Administrator password to set in instance.
        :param network_info:
           :py:meth:`~nova.network.manager.NetworkManager.get_instance_nw_info`
        :param block_device_info: Information about block devices to be
                                  attached to the instance.
        :param flavor: The flavor for the instance to be spawned.
        """
        self._vbox_ops.spawn(context, instance, image_meta, injected_files,
                             admin_password, network_info, block_device_info)
        self._console_ops.prepare_instance(instance)
        self._vbox_ops.power_on(instance)

    def destroy(self, context, instance, network_info, block_device_info=None,
                destroy_disks=True, migrate_data=None):
        """Destroy the specified instance from the Hypervisor.

        If the instance is not found (for example if networking failed), this
        function should still succeed.  It's probably a good idea to log a
        warning in that case.

        :param context: security context
        :param instance: Instance object as returned by DB layer.
        :param network_info:
           :py:meth:`~nova.network.manager.NetworkManager.get_instance_nw_info`
        :param block_device_info: Information about block devices that should
                                  be detached from the instance.
        :param destroy_disks: Indicates if disks should be destroyed
        :param migrate_data: implementation specific params
        """
        self._console_ops.cleanup(instance)
        self._vbox_ops.destroy(instance, context, network_info,
                               block_device_info, destroy_disks,
                               migrate_data)

    def cleanup_host(self, host):
        """Clean up anything that is necessary for the driver gracefully stop,
        including ending remote sessions. This is optional.
        """
        pass

    def pause(self, instance):
        """Pause the specified instance.

        :param instance: Instance object as returned by DB layer.
        """
        self._vbox_ops.pause(instance)

    def unpause(self, instance):
        """Unpause paused VM instance.

        :param instance: Instance object as returned by DB layer.
        """
        self._vbox_ops.unpause(instance)

    def suspend(self, context, instance):
        """suspend the specified instance.

        :param context: the context for the suspend
        :param instance: nova.objects.instance.Instance
        """
        self._vbox_ops.suspend(instance)

    def resume(self, context, instance, network_info, block_device_info=None):
        """Resume the specified instance.

        :param context: the context for the resume
        :param instance: nova.objects.instance.Instance being resumed
        :param network_info:
           :py:meth:`~nova.network.manager.NetworkManager.get_instance_nw_info`
        :param block_device_info: instance volume block device info
        """
        self._vbox_ops.resume(instance, context, network_info,
                              block_device_info)

    def reboot(self, context, instance, network_info, reboot_type,
               block_device_info=None, bad_volumes_callback=None):
        """Reboot the specified instance.

        After this is called successfully, the instance's state
        goes back to power_state.RUNNING. The virtualization
        platform should ensure that the reboot action has completed
        successfully even in cases in which the underlying domain/vm
        is paused or halted/stopped.

        :param instance: nova.objects.instance.Instance
        :param network_info:
           :py:meth:`~nova.network.manager.NetworkManager.get_instance_nw_info`
        :param reboot_type: Either a HARD or SOFT reboot
        :param block_device_info: Info pertaining to attached volumes
        :param bad_volumes_callback: Function to handle any bad volumes
            encountered
        """
        self._vbox_ops.reboot(instance, context, network_info, reboot_type,
                              block_device_info, bad_volumes_callback)

    def power_off(self, instance, timeout=0, retry_interval=0):
        """Power off the specified instance.

        :param instance: nova.objects.instance.Instance
        :param timeout: time to wait for GuestOS to shutdown
        :param retry_interval: How often to signal guest while
                               waiting for it to shutdown
        """
        self._vbox_ops.power_off(instance, timeout, retry_interval)
        self._console_ops.cleanup(instance)

    def power_on(self, context, instance, network_info,
                 block_device_info=None):
        """Power on the specified instance.

        :param instance: nova.objects.instance.Instance
        """
        self._console_ops.prepare_instance(instance)
        self._vbox_ops.power_on(instance, context, network_info,
                                block_device_info)

    def snapshot(self, context, instance, image_id, update_task_state):
        """Snapshots the specified instance.

        :param context: security context
        :param instance: nova.objects.instance.Instance
        :param image_id: Reference to a pre-created image that will
                         hold the snapshot.
        """
        self._snapshot_ops.take_snapshot(context, instance,
                                         image_id, update_task_state)

    def get_rdp_console(self, context, instance):
        """Get connection info for a rdp console.

        :param context: security context
        :param instance: nova.objects.instance.Instance

        :returns an instance of console.type.ConsoleRDP
        """
        return self._console_ops.get_rdp_console(instance)

    def get_vnc_console(self, context, instance):
        """Get connection info for a vnc console.

        :param context: security context
        :param instance: nova.objects.instance.Instance

        :returns an instance of console.type.ConsoleVNC
        """
        return self._console_ops.get_vnc_console(instance)

    def attach_volume(self, context, connection_info, instance, mountpoint,
                      disk_bus=None, device_type=None, encryption=None):
        """Attach the disk to the instance at mountpoint using info."""
        self._volume_ops.attach_volume(instance, connection_info)

    def detach_volume(self, connection_info, instance, mountpoint,
                      encryption=None):
        """Detach the disk attached to the instance."""
        self._volume_ops.detach_volume(instance, connection_info)

    def get_volume_connector(self, instance):
        """Get connector information for the instance for attaching to volumes.

        Connector information is a dictionary representing the ip of the
        machine that will be making the connection, the name of the iscsi
        initiator and the hostname of the machine as follows::

            {
                'ip': ip,
                'initiator': initiator,
                'host': hostname
            }
        """
        return self._volume_ops.get_volume_connector(instance)

    def migrate_disk_and_power_off(self, context, instance, dest,
                                   flavor, network_info,
                                   block_device_info=None,
                                   timeout=0, retry_interval=0):
        """Transfers the disk of a running instance in multiple phases, turning
        off the instance before the end.

        :param instance: nova.objects.instance.Instance
        :param timeout: time to wait for GuestOS to shutdown
        :param retry_interval: How often to signal guest while
                               waiting for it to shutdown
        """
        self._console_ops.cleanup(instance)
        return self._migrationops.migrate_disk_and_power_off(
            context, instance, dest, flavor, network_info, block_device_info,
            timeout, retry_interval)

    def finish_migration(self, context, migration, instance, disk_info,
                         network_info, image_meta, resize_instance,
                         block_device_info=None, power_on=True):
        """Completes a resize.

        :param context: the context for the migration/resize
        :param migration: the migrate/resize information
        :param instance: nova.objects.instance.Instance being migrated/resized
        :param disk_info: the newly transferred disk information
        :param network_info:
           :py:meth:`~nova.network.manager.NetworkManager.get_instance_nw_info`
        :param image_meta: image object returned by nova.image.glance that
                           defines the image from which this instance
                           was created
        :param resize_instance: True if the instance is being resized,
                                False otherwise
        :param block_device_info: instance volume block device info
        :param power_on: True if the instance should be powered on, False
                         otherwise
        """
        self._migrationops.finish_migration(
            context, migration, instance, disk_info, network_info,
            image_meta, resize_instance, block_device_info)

        if power_on:
            self._console_ops.prepare_instance(instance)
            self._vbox_ops.power_on(instance)

    def confirm_migration(self, migration, instance, network_info):
        """Confirms a resize, destroying the source VM.

        :param instance: nova.objects.instance.Instance
        """
        self._migrationops.confirm_migration(migration, instance, network_info)

    def finish_revert_migration(self, context, instance, network_info,
                                block_device_info=None, power_on=True):
        """Finish reverting a resize.

        :param context: the context for the finish_revert_migration
        :param instance: nova.objects.instance.Instance being migrated/resized
        :param network_info:
           :py:meth:`~nova.network.manager.NetworkManager.get_instance_nw_info`
        :param block_device_info: instance volume block device info
        :param power_on: True if the instance should be powered on, False
                         otherwise
        """
        self._migrationops.finish_revert_migration(
            context, instance, network_info, block_device_info)

        if power_on:
            self._console_ops.prepare_instance(instance)
            self._vbox_ops.power_on(instance)

    def get_host_ip_addr(self):
        """Retrieves the IP address of the dom0
        """
        return hostops.get_host_ip_address()
