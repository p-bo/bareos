#!/usr/bin/env python
# -*- coding: utf-8 -*-
# BAREOS® - Backup Archiving REcovery Open Sourced
#
# Copyright (C) 2014-2014 Bareos GmbH & Co. KG
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of version three of the GNU Affero General Public
# License as published by the Free Software Foundation, which is
# listed in the file LICENSE.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.
#
# Author: Stephan Duehr
#
# Bareos python class for VMware related backup and restore
#

import bareosfd
from bareos_fd_consts import bJobMessageType, bFileType, bRCs, bIOPS
from bareos_fd_consts import bEventType, bVariable, bCFs
import BareosFdPluginBaseclass
import json
import os
import time
import tempfile
import subprocess
import shlex

# if OrderedDict is not available from collection (eg. SLES11),
# the additional package python-ordereddict must be used
try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict

from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
from pyVmomi import vmodl


class BareosFdPluginVMware(BareosFdPluginBaseclass.BareosFdPluginBaseclass):
    '''
    VMware related backup and restore BAREOS fd-plugin methods
    '''
    def __init__(self, context, plugindef):
        bareosfd.DebugMessage(
            context, 100,
            "Constructor called in module %s with plugindef=%s\n" %
            (__name__, plugindef))
        super(BareosFdPluginVMware, self).__init__(context, plugindef)
        self.events = []
        self.events.append(bEventType['bEventStartBackupJob'])
        self.events.append(bEventType['bEventStartRestoreJob'])
        bareosfd.RegisterEvents(context, self.events)
        self.mandatory_options_default = ['vcserver', 'vcuser', 'vcpass']
        self.mandatory_options_vmname = ['dc', 'folder', 'vmname']

        self.vadp = BareosVADPWrapper()

    def parse_plugin_definition(self, context, plugindef):
        '''
        Parses the plugin arguments
        '''
        bareosfd.DebugMessage(
            context, 100,
            "parse_plugin_definition() was called in module %s\n" %
            (__name__))
        super(BareosFdPluginVMware, self).parse_plugin_definition(
            context, plugindef)
        self.vadp.options = self.options

        return bRCs['bRC_OK']

    def check_options(self, context, mandatory_options=None):
        '''
        Check Plugin options
        '''
        if mandatory_options is None:
            # not passed, use default
            mandatory_options = self.mandatory_options_default
            if 'uuid' not in self.options:
                mandatory_options += self.mandatory_options_vmname

        for option in mandatory_options:
            if (option not in self.options):
                bareosfd.DebugMessage(
                    context, 100, "Option \'%s\' not defined.\n" %
                    (option))
                bareosfd.JobMessage(
                    context, bJobMessageType['M_FATAL'],
                    "Option \'%s\' not defined.\n" %
                    option)

                return bRCs['bRC_Error']

            bareosfd.DebugMessage(
                context, 100, "Using Option %s=%s\n" %
                (option, self.options[option]))

        return bRCs['bRC_OK']

    def start_backup_job(self, context):
        '''
        Start of Backup Job
        '''
        check_option_bRC = self.check_options(context)
        if check_option_bRC != bRCs['bRC_OK']:
            return check_option_bRC

        if not self.vadp.connect_vmware(context):
            return bRCs['bRC_Error']

        return self.vadp.prepare_vm_backup(context)

    def start_backup_file(self, context, savepkt):
        '''
        Defines the file to backup and creates the savepkt.
        '''
        bareosfd.DebugMessage(
            context, 100,
            "BareosFdPluginVMware:start_backup_file() called\n")

        if not self.vadp.files_to_backup:
            self.vadp.disk_device_to_backup = self.vadp.disk_devices.pop(0)
            self.vadp.files_to_backup = []
            if 'uuid' in self.options:
                self.vadp.files_to_backup.append('/VMS/%s/%s' % (
                    self.options['uuid'],
                    self.vadp.disk_device_to_backup['fileNameRoot'])
                    )
            else:
                self.vadp.files_to_backup.append('/VMS/%s%s/%s/%s' % (
                    self.options['dc'],
                    self.options['folder'].rstrip('/'),
                    self.options['vmname'],
                    self.vadp.disk_device_to_backup['fileNameRoot'])
                    )

            self.vadp.files_to_backup.insert(
                0,
                self.vadp.files_to_backup[0] + '_cbt.json')

        self.vadp.file_to_backup = self.vadp.files_to_backup.pop(0)

        bareosfd.DebugMessage(
            context, 100,
            "file: %s\n" %
            (self.vadp.file_to_backup))
        if self.vadp.file_to_backup.endswith('_cbt.json'):
            if not self.vadp.get_vm_disk_cbt(context):
                return bRCs['bRC_Error']

            # create a stat packet for a restore object
            statp = bareosfd.StatPacket()
            savepkt.statp = statp
            # see src/filed/backup.c how this is done in c
            savepkt.type = bFileType['FT_RESTORE_FIRST']
            # set the fname of the restore object to the vmdk name
            # by stripping of the _cbt.json suffix
            v_fname = self.vadp.file_to_backup[:-len('_cbt.json')]
            if chr(self.level) != 'F':
                # add level and timestamp to fname in savepkt
                savepkt.fname = "%s+%s+%s" % (v_fname,
                                              chr(self.level),
                                              repr(self.vadp.create_snap_tstamp))
            else:
                savepkt.fname = v_fname

            savepkt.object_name = savepkt.fname
            savepkt.object = bytearray(self.vadp.changed_disk_areas_json)
            savepkt.object_len = len(savepkt.object)
            savepkt.object_index = int(time.time())

        else:
            # start bareos_vadp_dumper
            self.vadp.start_dumper(context, 'dump')

            # create a regular stat packet
            statp = bareosfd.StatPacket()
            savepkt.statp = statp
            savepkt.fname = self.vadp.file_to_backup
            if chr(self.level) != 'F':
                # add level and timestamp to fname in savepkt
                savepkt.fname = "%s+%s+%s" % (self.vadp.file_to_backup,
                                              chr(self.level),
                                              repr(self.vadp.create_snap_tstamp))
            savepkt.type = bFileType['FT_REG']

        bareosfd.JobMessage(
            context, bJobMessageType['M_INFO'],
            "Starting backup of %s\n" %
            self.vadp.file_to_backup)
        return bRCs['bRC_OK']

    def start_restore_job(self, context):
        '''
        Start of Restore Job
        '''
        check_option_bRC = self.check_options(context)
        if check_option_bRC != bRCs['bRC_OK']:
            return check_option_bRC

        if not self.vadp.connect_vmware(context):
            return bRCs['bRC_Error']

        return self.vadp.prepare_vm_restore(context)

    def start_restore_file(self, context, cmd):
        bareosfd.DebugMessage(
            context, 100,
            "BareosFdPluginVMware:start_restore_file() called with %s\n" %
            (cmd))
        return bRCs['bRC_OK']

    def create_file(self, context, restorepkt):
        '''
        For the time being, assumes that the virtual disk already
        exists with the same name that has been backed up.
        This should work for restoring the same VM.
        For restoring to a new different VM, additional steps
        must be taken, because the disk path will be different.
        '''
        bareosfd.DebugMessage(
            context, 100,
            "BareosFdPluginVMware:create_file() called with %s\n" %
            (restorepkt))

        tmp_path = '/var/tmp/bareos-vmware-plugin'
        objectname = '/' + os.path.relpath(restorepkt.ofname, restorepkt.where)
        json_filename = tmp_path + objectname + '_cbt.json'
        # for now, restore requires no snapshot to exist so disk to
        # be written must be the the root-disk, even if a manual snapshot
        # existed when the backup was run. So the diskPath in JSON will
        # be set to diskPathRoot
        cbt_data = self.vadp.restore_objects_by_objectname[objectname]['data']
        cbt_data['DiskParams']['diskPath'] = cbt_data['DiskParams']['diskPathRoot']
        self.vadp.writeStringToFile(context,
                                    json_filename,
                                    json.dumps(cbt_data))
        self.cbt_json_local_file_path = json_filename
        self.vadp.start_dumper(context, 'restore')
        if restorepkt.type == bFileType['FT_REG']:
            restorepkt.create_status = bCFs['CF_EXTRACT']
        return bRCs['bRC_OK']

    def plugin_io(self, context, IOP):
        bareosfd.DebugMessage(
            context, 100,
            "BareosFdPluginVMware:plugin_io() called with function %s\n" %
            (IOP.func))
        bareosfd.DebugMessage(
            context, 100, "self.FNAME is set to %s\n" % (self.FNAME))

        self.vadp.keepalive()

        if IOP.func == bIOPS['IO_OPEN']:
            self.FNAME = IOP.fname
            bareosfd.DebugMessage(
                context, 100,
                "self.FNAME was set to %s from IOP.fname\n" %
                (self.FNAME))
            try:
                if IOP.flags & (os.O_CREAT | os.O_WRONLY):
                    bareosfd.DebugMessage(
                        context, 100,
                        "Open file %s for writing with %s\n" %
                        (self.FNAME, IOP))

                    # this is a restore
                    # create_file() should have started
                    # bareos_vadp_dumper, check:
                    if self.vadp.dumper_process:
                        bareosfd.DebugMessage(
                            context, 100,
                            ("plugin_io: bareos_vadp_dumper running with"
                             " PID %s\n") %
                            (self.vadp.dumper_process.pid))
                    else:
                        bareosfd.JobMessage(
                            context, bJobMessageType['M_FATAL'],
                            "plugin_io: bareos_vadp_dumper not running\n")
                        return bRCs['bRC_Error']

                else:
                    bareosfd.DebugMessage(
                        context, 100,
                        "plugin_io: trying to open %s for reading\n" %
                        (self.FNAME))
                    # this is a backup
                    # start_backup_file() should have started
                    # bareos_vadp_dumper, check:
                    if self.vadp.dumper_process:
                        bareosfd.DebugMessage(
                            context, 100,
                            ("plugin_io: bareos_vadp_dumper running with"
                             " PID %s\n") %
                            (self.vadp.dumper_process.pid))
                    else:
                        bareosfd.JobMessage(
                            context, bJobMessageType['M_FATAL'],
                            "plugin_io: bareos_vadp_dumper not running\n")
                        return bRCs['bRC_Error']

            except:
                IOP.status = -1
                bareosfd.DebugMessage(
                    context, 100, "plugin_io: failed to open %s\n" %
                    (self.FNAME))
                bareosfd.JobMessage(
                    context, bJobMessageType['M_FATAL'],
                    "plugin_io: failed to open %s\n" %
                    (self.FNAME))
                return bRCs['bRC_Error']

            return bRCs['bRC_OK']

        elif IOP.func == bIOPS['IO_CLOSE']:
            if self.jobType == 'B':
                # Backup Job
                bareosfd.DebugMessage(
                    context, 100,
                    ("plugin_io: calling end_dumper() to wait for"
                     " PID %s to terminate\n") %
                    (self.vadp.dumper_process.pid))
                bareos_vadp_dumper_returncode = self.vadp.end_dumper(context)
                if bareos_vadp_dumper_returncode != 0:
                    bareosfd.JobMessage(
                        context, bJobMessageType['M_FATAL'],
                        ("plugin_io[IO_CLOSE]: bareos_vadp_dumper returncode:"
                         " %s\n") %
                        (bareos_vadp_dumper_returncode))
                    return bRCs['bRC_Error']

            elif self.jobType == 'R':
                # Restore Job
                bareosfd.DebugMessage(
                    context, 100,
                    "Closing Pipe to bareos_vadp_dumper for %s\n" %
                    (self.FNAME))
                self.vadp.dumper_process.stdin.close()
                bareosfd.DebugMessage(
                    context, 100,
                    ("plugin_io: calling end_dumper() to wait for"
                     " PID %s to terminate\n") %
                    (self.vadp.dumper_process.pid))
                bareos_vadp_dumper_returncode = self.vadp.end_dumper(context)
                if bareos_vadp_dumper_returncode != 0:
                    bareosfd.JobMessage(
                        context, bJobMessageType['M_FATAL'],
                        ("plugin_io[IO_CLOSE]: bareos_vadp_dumper returncode:"
                         " %s\n") %
                        (bareos_vadp_dumper_returncode))
                    return bRCs['bRC_Error']

            else:
                bareosfd.JobMessage(
                    context, bJobMessageType['M_FATAL'],
                    "plugin_io[IO_CLOSE]: unknown Job Type %s\n" %
                    (self.jobType))
                return bRCs['bRC_Error']

            return bRCs['bRC_OK']

        elif IOP.func == bIOPS['IO_SEEK']:
            return bRCs['bRC_OK']

        elif IOP.func == bIOPS['IO_READ']:
            IOP.buf = bytearray(IOP.count)
            IOP.status = self.vadp.dumper_process.stdout.readinto(
                IOP.buf)
            IOP.io_errno = 0

            return bRCs['bRC_OK']

        elif IOP.func == bIOPS['IO_WRITE']:
            self.vadp.dumper_process.stdin.write(IOP.buf)
            IOP.status = IOP.count
            IOP.io_errno = 0
            return bRCs['bRC_OK']

    def handle_plugin_event(self, context, event):
        if event in self.events:
            self.jobType = chr(bareosfd.GetValue(context, bVariable['bVarType']))
            bareosfd.DebugMessage(
                context, 100,
                "jobType: %s\n" %
                (self.jobType))

        if event == bEventType['bEventJobEnd']:
            bareosfd.DebugMessage(
                context, 100,
                "handle_plugin_event() called with bEventJobEnd\n")
            bareosfd.DebugMessage(
                context, 100,
                "Disconnecting from VSphere API on host %s with user %s\n" %
                (self.options['vcserver'], self.options['vcuser']))

            self.vadp.cleanup()

        elif event == bEventType['bEventEndBackupJob']:
            bareosfd.DebugMessage(
                context, 100,
                "handle_plugin_event() called with bEventEndBackupJob\n")
            bareosfd.DebugMessage(
                context, 100,
                "removing Snapshot\n")
            self.vadp.remove_vm_snapshot(context)

        elif event == bEventType['bEventEndFileSet']:
            bareosfd.DebugMessage(
                context, 100,
                "handle_plugin_event() called with bEventEndFileSet\n")

        elif event == bEventType['bEventStartBackupJob']:
            bareosfd.DebugMessage(
                context, 100,
                "handle_plugin_event() called with bEventStartBackupJob\n")

            return self.start_backup_job(context)

        elif event == bEventType['bEventStartRestoreJob']:
            bareosfd.DebugMessage(
                context, 100,
                "handle_plugin_event() called with bEventStartRestoreJob\n")

            return self.start_restore_job(context)

        else:
            bareosfd.DebugMessage(
                context, 100,
                "handle_plugin_event() called with event %s\n" %
                (event))

        return bRCs['bRC_OK']

    def end_backup_file(self, context):
        bareosfd.DebugMessage(
            context, 100,
            "BareosFdPluginVMware:end_backup_file() called\n")
        if self.vadp.disk_devices or self.vadp.files_to_backup:
            bareosfd.DebugMessage(
                context, 100,
                "end_backup_file(): returning bRC_More\n")
            return bRCs['bRC_More']

        bareosfd.DebugMessage(
            context, 100,
            "end_backup_file(): returning bRC_OK\n")
        return bRCs['bRC_OK']

    def restore_object_data(self, context, ROP):
        """
        Note:
        This is called in two cases:
        - on diff/inc backup (should be called only once)
        - on restore (for every job id being restored)
        But at the point in time called, it is not possible
        to distinguish which of them it is, because job type
        is "I" until the bEventStartBackupJob event
        """
        bareosfd.DebugMessage(
            context, 100,
            "BareosFdPluginVMware:restore_object_data() called with ROP:%s\n" %
            (ROP))
        bareosfd.DebugMessage(
            context, 100,
            "ROP.object_name(%s): %s\n" %
            (type(ROP.object_name), ROP.object_name))
        bareosfd.DebugMessage(
            context, 100,
            "ROP.plugin_name(%s): %s\n" %
            (type(ROP.plugin_name), ROP.plugin_name))
        bareosfd.DebugMessage(
            context, 100,
            "ROP.object_len(%s): %s\n" %
            (type(ROP.object_len), ROP.object_len))
        bareosfd.DebugMessage(
            context, 100,
            "ROP.object_full_len(%s): %s\n" %
            (type(ROP.object_full_len), ROP.object_full_len))
        bareosfd.DebugMessage(
            context, 100,
            "ROP.object(%s): %s\n" %
            (type(ROP.object), ROP.object))
        ro_data = self.vadp.json2cbt(str(ROP.object))
        ro_filename = ro_data['DiskParams']['diskPathRoot']
        # self.vadp.restore_objects_by_diskpath is used on backup
        # in get_vm_disk_cbt()
        # self.vadp.restore_objects_by_objectname is used on restore
        # by create_file()
        self.vadp.restore_objects_by_diskpath[ro_filename] = []
        self.vadp.restore_objects_by_diskpath[ro_filename].append(
            {'json': ROP.object,
             'data': ro_data})
        self.vadp.restore_objects_by_objectname[ROP.object_name] = \
            self.vadp.restore_objects_by_diskpath[ro_filename][-1]
        return bRCs['bRC_OK']


class BareosVADPWrapper(object):
    '''
    VADP specific class.
    '''
    def __init__(self):
        self.si = None
        self.si_last_keepalive = None
        self.vm = None
        self.create_snap_task = None
        self.create_snap_result = None
        self.file_to_backup = None
        self.files_to_backup = None
        self.disk_devices = None
        self.disk_device_to_backup = None
        self.cbt_json_local_file_path = None
        self.dumper_process = None
        self.changed_disk_areas_json = None
        self.restore_objects_by_diskpath = {}
        self.restore_objects_by_objectname = {}
        self.options = None
        self.skip_disk_modes = ['independent_nonpersistent',
                                'independent_persistent']

    def connect_vmware(self, context):
        # this prevents from repeating on second call
        if self.si:
            bareosfd.DebugMessage(
                context, 100,
                "connect_vmware(): connection to server %s already exists\n" %
                (self.options['vcserver']))
            return True

        bareosfd.DebugMessage(
            context, 100,
            "connect_vmware(): connecting server %s\n" %
            (self.options['vcserver']))
        try:
            self.si = SmartConnect(host=self.options['vcserver'],
                                   user=self.options['vcuser'],
                                   pwd=self.options['vcpass'],
                                   port=443)
            self.si_last_keepalive = int(time.time())

        except IOError:
            pass
        if not self.si:
            bareosfd.JobMessage(
                context, bJobMessageType['M_FATAL'],
                "Cannot connect to host %s with user %s and password\n" %
                (self.options['vcserver'], self.options['vcuser']))
            return False

        bareosfd.DebugMessage(
            context, 100,
            ("Successfully connected to VSphere API on host %s with"
             " user %s\n") %
            (self.options['vcserver'], self.options['vcuser']))

        return True

    def cleanup(self):
        Disconnect(self.si)
        # the Disconnect Method does not close the tcp connection
        # is that so intentionally?
        # However, explicitly closing it works like this:
        self.si._stub.DropConnections()
        self.si = None
        self.log = None

    def keepalive(self):
        # FIXME: prevent from vSphere API timeout, needed until pyvmomi fixes
        # https://github.com/vmware/pyvmomi/issues/239
        # otherwise idle timeout occurs after 20 minutes (1200s),
        # so call CurrentTime() every 15min (900s) to keep alive
        if int(time.time()) - self.si_last_keepalive > 900:
            self.si.CurrentTime()
            self.si_last_keepalive = int(time.time())

    def prepare_vm_backup(self, context):
        '''
        prepare VM backup:
        - get vm details
        - take snapshot
        - get disk devices
        '''
        if 'uuid' in self.options:
            vmname = self.options['uuid']
            if not self.get_vm_details_by_uuid(context):
                bareosfd.DebugMessage(
                    context, 100, "Error getting details for VM %s\n" %
                    (vmname))
                return bRCs['bRC_Error']
        else:
            vmname = self.options['vmname']
            if not self.get_vm_details_dc_folder_vmname(context):
                bareosfd.DebugMessage(
                    context, 100, "Error getting details for VM %s\n" %
                    (vmname))
                return bRCs['bRC_Error']

        bareosfd.DebugMessage(
            context, 100, "Successfully got details for VM %s\n" %
            (vmname))

        # check if the VM supports CBT and that CBT is enabled
        if not self.vm.capability.changeTrackingSupported:
            bareosfd.JobMessage(
                context, bJobMessageType['M_FATAL'],
                "Error VM %s does not support CBT\n" %
                (vmname))
            return bRCs['bRC_Error']

        if not self.vm.config.changeTrackingEnabled:
            bareosfd.JobMessage(
                context, bJobMessageType['M_FATAL'],
                "Error VM %s is not CBT enabled\n" %
                (vmname))
            return bRCs['bRC_Error']

        bareosfd.DebugMessage(
            context, 100, "Creating Snapshot on VM %s\n" %
            (vmname))

        if not self.create_vm_snapshot(context):
            bareosfd.JobMessage(
                context, bJobMessageType['M_FATAL'],
                "Error creating snapshot on VM %s\n" %
                (vmname))
            return bRCs['bRC_Error']

        bareosfd.DebugMessage(
            context, 100,
            "Successfully created snapshot on VM %s\n" %
            (vmname))

        bareosfd.DebugMessage(
            context, 100, "Getting Disk Devices on VM %s from snapshot\n" %
            (vmname))
        self.get_vm_snap_disk_devices(context)
        if not self.disk_devices:
            bareosfd.JobMessage(
                context, bJobMessageType['M_FATAL'],
                "Error getting Disk Devices on VM %s from snapshot\n" %
                (vmname))
            return bRCs['bRC_Error']

        return bRCs['bRC_OK']

    def prepare_vm_restore(self, context):
        '''
        prepare VM restore:
        - get vm details
        - ensure vm is powered off
        - get disk devices
        '''
        if 'uuid' in self.options:
            vmname = self.options['uuid']
            if not self.get_vm_details_by_uuid(context):
                bareosfd.DebugMessage(
                    context, 100, "Error getting details for VM %s\n" %
                    (vmname))
                return bRCs['bRC_Error']
        else:
            vmname = self.options['vmname']
            if not self.get_vm_details_dc_folder_vmname(context):
                bareosfd.DebugMessage(
                    context, 100, "Error getting details for VM %s\n" %
                    (vmname))
                return bRCs['bRC_Error']

        bareosfd.DebugMessage(
            context, 100, "Successfully got details for VM %s\n" %
            (vmname))

        vm_power_state = self.vm.summary.runtime.powerState
        if vm_power_state != 'poweredOff':
            bareosfd.JobMessage(
                context, bJobMessageType['M_FATAL'],
                "Error VM %s must be poweredOff for restore, but is %s\n" %
                (vmname, vm_power_state))
            return bRCs['bRC_Error']

        if self.vm.snapshot is not None:
            bareosfd.JobMessage(
                context, bJobMessageType['M_FATAL'],
                "Error VM %s must not have any snapshots before restore\n" %
                (vmname))
            return bRCs['bRC_Error']

        bareosfd.DebugMessage(
            context, 100, "Getting Disk Devices on VM %s\n" %
            (vmname))
        self.get_vm_disk_devices(context)
        if not self.disk_devices:
            bareosfd.JobMessage(
                context, bJobMessageType['M_FATAL'],
                "Error getting Disk Devices on VM %s\n" %
                (vmname))
            return bRCs['bRC_Error']

        # make sure backed up disks match VM disks
        if not self.check_vm_disks_match(context):
            return bRCs['bRC_Error']

        return bRCs['bRC_OK']

    def get_vm_details_dc_folder_vmname(self, context):
        '''
        Get details of VM given by plugin options dc, folder, vmname
        and save result in self.vm
        Returns True on success, False otherwise
        '''
        content = self.si.content
        dcView = content.viewManager.CreateContainerView(content.rootFolder,
                                                         [vim.Datacenter],
                                                         False)
        vmListWithFolder = {}
        dcList = dcView.view
        dcView.Destroy()
        for dc in dcList:
            if dc.name == self.options['dc']:
                folder = ''
                self._get_dcftree(vmListWithFolder, folder, dc.vmFolder)

        if self.options['folder'].endswith('/'):
            vm_path = "%s%s" % (self.options['folder'], self.options['vmname'])
        else:
            vm_path = "%s/%s" % (self.options['folder'], self.options['vmname'])

        if vm_path not in vmListWithFolder:
            bareosfd.JobMessage(
                context, bJobMessageType['M_FATAL'],
                "No VM with Folder/Name %s found in DC %s\n" %
                (vm_path, self.options['dc']))
            return False

        self.vm = vmListWithFolder[vm_path]
        return True

    def get_vm_details_by_uuid(self, context):
        '''
        Get details of VM given by plugin options uuid
        and save result in self.vm
        Returns True on success, False otherwise
        '''
        search_index = self.si.content.searchIndex
        self.vm = search_index.FindByUuid(None, self.options['uuid'], True, True)
        if self.vm is None:
            return False
        else:
            return True

    def _get_dcftree(self, dcf, folder, vm_folder):
        '''
        Recursive function to get VMs with folder names
        '''
        for vm_or_folder in vm_folder.childEntity:
            if isinstance(vm_or_folder, vim.VirtualMachine):
                dcf[folder + '/' + vm_or_folder.name] = vm_or_folder
            elif isinstance(vm_or_folder, vim.Folder):
                self._get_dcftree(dcf, folder + '/' + vm_or_folder.name, vm_or_folder)

    def create_vm_snapshot(self, context):
        '''
        Creates a snapshot
        '''
        try:
            self.create_snap_task = self.vm.CreateSnapshot_Task(
                name='BareosTmpSnap',
                description='Description for BareosTmpSnap',
                memory=False,
                quiesce=True)
        except vmodl.MethodFault as e:
            bareosfd.JobMessage(
                context, bJobMessageType['M_FATAL'],
                "Failed to create snapshot %s\n" % (e.msg))
            return False

        self.vmomi_WaitForTasks([self.create_snap_task])
        self.create_snap_result = self.create_snap_task.info.result
        self.create_snap_tstamp = time.time()
        return True

    def remove_vm_snapshot(self, context):
        '''
        Removes the snapshot taken before
        '''
        if not self.create_snap_result:
            bareosfd.JobMessage(
                context, bJobMessageType['M_WARNING'],
                "No snapshot was taken, skipping snapshot removal\n")
            return False

        try:
            rmsnap_task = \
                self.create_snap_result.RemoveSnapshot_Task(
                    removeChildren=True)
        except vmodl.MethodFault as e:
            bareosfd.JobMessage(
                context, bJobMessageType['M_WARNING'],
                "Failed to remove snapshot %s\n" % (e.msg))
            return False

        self.vmomi_WaitForTasks([rmsnap_task])
        return True

    def get_vm_snap_disk_devices(self, context):
        '''
        Get the disk devices from the created snapshot
        Assumption: Snapshot successfully created
        '''
        self.get_disk_devices(context, self.create_snap_result.config.hardware.device)

    def get_vm_disk_devices(self, context):
        '''
        Get the disk devices from vm
        '''
        self.get_disk_devices(context, self.vm.config.hardware.device)

    def get_disk_devices(self, context, devicespec):
        '''
        Get disk devices from a devicespec
        '''
        self.disk_devices = []
        for hw_device in devicespec:
            if type(hw_device) == vim.vm.device.VirtualDisk:
                if hw_device.backing.diskMode in self.skip_disk_modes:
                    bareosfd.JobMessage(
                        context, bJobMessageType['M_INFO'],
                        "Skipping Disk %s because mode is %s\n" %
                        (self.get_vm_disk_root_filename(hw_device.backing),
                         hw_device.backing.diskMode))
                    continue

                self.disk_devices.append(
                    {'deviceKey': hw_device.key,
                     'fileName': hw_device.backing.fileName,
                     'fileNameRoot': self.get_vm_disk_root_filename(
                         hw_device.backing),
                     'changeId': hw_device.backing.changeId})

    def get_vm_disk_root_filename(self, disk_device_backing):
        '''
        Get the disk name from the ende of the parents chain
        When snapshots exist, the original disk filename is
        needed. If no snapshots exist, the disk has no parent
        and the filename is the same.
        '''
        actual_backing = disk_device_backing
        while actual_backing.parent:
            actual_backing = actual_backing.parent
        return actual_backing.fileName

    def get_vm_disk_cbt(self, context):
        '''
        Get CBT Information
        '''
        cbt_changeId = '*'
        if self.disk_device_to_backup['fileNameRoot'] in self.restore_objects_by_diskpath:
            if len(self.restore_objects_by_diskpath[
                    self.disk_device_to_backup['fileNameRoot']]) > 1:
                bareosfd.JobMessage(
                    context, bJobMessageType['M_FATAL'],
                    "ERROR: more then one CBT info for Diff/Inc exists\n")
                return False

            cbt_changeId = self.restore_objects_by_diskpath[
                self.disk_device_to_backup['fileNameRoot']][0][
                    'data']['DiskParams']['changeId']
            bareosfd.DebugMessage(
                context, 100,
                "get_vm_disk_cbt(): using changeId %s from restore object\n" %
                (cbt_changeId))
        self.changed_disk_areas = self.vm.QueryChangedDiskAreas(
            snapshot=self.create_snap_result,
            deviceKey=self.disk_device_to_backup['deviceKey'],
            startOffset=0,
            changeId=cbt_changeId)
        self.cbt2json(context)
        return True

    def check_vm_disks_match(self, context):
        '''
        Check if the backed up disks match selecte VM disks
        '''
        backed_up_disks = set(self.restore_objects_by_diskpath.keys())
        vm_disks = set([disk_dev['fileNameRoot'] for disk_dev in self.disk_devices])

        if backed_up_disks == vm_disks:
            bareosfd.DebugMessage(
                context, 100,
                "check_vm_disks_match(): OK, VM disks match backed up disks\n")
            return True

        bareosfd.JobMessage(
            context, bJobMessageType['M_WARNING'],
            "VM Disks: %s\n" % (', '.join(vm_disks)))
        bareosfd.JobMessage(
            context, bJobMessageType['M_WARNING'],
            "Backed up Disks: %s\n" % (', '.join(backed_up_disks)))
        bareosfd.JobMessage(
            context, bJobMessageType['M_FATAL'],
            "ERROR: VM disks not matching backed up disks\n")
        return False

    def cbt2json(self, context):
        '''
        Convert CBT data into json serializable structure and
        return it as json string
        '''

        # the order of keys in JSON data must be preserved for
        # bareos_vadp_dumper to work properly, this is done
        # by using the OrderedDict type
        cbt_data = OrderedDict()
        cbt_data['ConnParams'] = {}
        cbt_data['ConnParams']['VmMoRef'] = 'moref=' + self.vm._moId
        cbt_data['ConnParams']['VsphereHostName'] = self.options['vcserver']
        cbt_data['ConnParams']['VsphereUsername'] = self.options['vcuser']
        cbt_data['ConnParams']['VspherePassword'] = self.options['vcpass']
        cbt_data['ConnParams'][
            'VsphereSnapshotMoRef'] = self.create_snap_result._moId

        # disk params for bareos_vadp_dumper
        cbt_data['DiskParams'] = {}
        cbt_data['DiskParams']['diskPath'] = self.disk_device_to_backup['fileName']
        cbt_data['DiskParams']['diskPathRoot'] = self.disk_device_to_backup['fileNameRoot']
        cbt_data['DiskParams']['changeId'] = self.disk_device_to_backup['changeId']

        # cbt data for bareos_vadp_dumper
        cbt_data['DiskChangeInfo'] = {}
        cbt_data['DiskChangeInfo']['startOffset'] = self.changed_disk_areas.startOffset
        cbt_data['DiskChangeInfo']['length'] = self.changed_disk_areas.length
        cbt_data['DiskChangeInfo']['changedArea'] = []
        for extent in self.changed_disk_areas.changedArea:
            cbt_data['DiskChangeInfo']['changedArea'].append(
                {'start': extent.start, 'length': extent.length})

        self.changed_disk_areas_json = json.dumps(cbt_data)
        self.writeStringToFile(
            context,
            '/var/tmp' +
            self.file_to_backup,
            self.changed_disk_areas_json)

    def json2cbt(self, cbt_json_string):
        '''
        Convert JSON string from restore object to ordered dict
        to preserve the key order required for bareos_vadp_dumper
        to work properly
        return OrderedDict
        '''

        # the order of keys in JSON data must be preserved for
        # bareos_vadp_dumper to work properly
        cbt_data = OrderedDict()
        cbt_keys_ordered = ['ConnParams', 'DiskParams', 'DiskChangeInfo']
        cbt_data_tmp = json.loads(cbt_json_string)
        for cbt_key in cbt_keys_ordered:
            cbt_data[cbt_key] = cbt_data_tmp[cbt_key]

        return cbt_data

    def dumpJSONfile(self, context, filename, data):
        """
        Write a Python data structure in JSON format to the given file.
        Note: obsolete, no longer used because order of keys in JSON
              string must be preserved
        """
        bareosfd.DebugMessage(
            context, 100, "dumpJSONfile(): writing JSON data to file %s\n" %
            (filename))
        try:
            out = open(filename, 'w')
            json.dump(data, out)
            out.close()
            bareosfd.DebugMessage(
                context, 100,
                "dumpJSONfile(): successfully wrote JSON data to file %s\n" %
                (filename))

        except IOError as io_error:
            bareosfd.JobMessage(
                context, bJobMessageType['M_FATAL'],
                ("dumpJSONFile(): failed to write JSON data to file %s,"
                 " reason: %s\n")
                % (filename, io_error.strerror))

    def writeStringToFile(self, context, filename, data_string):
        """
        Write a String to the given file.
        """
        bareosfd.DebugMessage(
            context, 100, "writeStringToFile(): writing String to file %s\n" %
            (filename))
        # ensure the directory for writing the file exists
        self.mkdir(os.path.dirname(filename))
        try:
            out = open(filename, 'w')
            out.write(data_string)
            out.close()
            bareosfd.DebugMessage(
                context, 100,
                "saveStringTofile(): successfully wrote String to file %s\n" %
                (filename))

        except IOError as io_error:
            bareosfd.JobMessage(
                context, bJobMessageType['M_FATAL'],
                ("writeStingToFile(): failed to write String to file %s,"
                 " reason: %s\n")
                % (filename, io_error.strerror))

        # the following path must be passed to bareos_vadp_dumper as parameter
        self.cbt_json_local_file_path = filename

    def vmomi_WaitForTasks(self, tasks):
        """
        Given the service instance si and tasks, it returns after all the
        tasks are complete
        """

        si = self.si
        pc = si.content.propertyCollector

        taskList = [str(task) for task in tasks]

        # Create filter
        objSpecs = [vmodl.query.PropertyCollector.ObjectSpec(obj=task)
                    for task in tasks]
        propSpec = vmodl.query.PropertyCollector.PropertySpec(
            type=vim.Task,
            pathSet=[],
            all=True)
        filterSpec = vmodl.query.PropertyCollector.FilterSpec()
        filterSpec.objectSet = objSpecs
        filterSpec.propSet = [propSpec]
        pcfilter = pc.CreateFilter(filterSpec, True)

        try:
            version, state = None, None

            # Loop looking for updates till the state moves to a completed
            # state.
            while len(taskList):
                update = pc.WaitForUpdates(version)
                for filterSet in update.filterSet:
                    for objSet in filterSet.objectSet:
                        task = objSet.obj
                        for change in objSet.changeSet:
                            if change.name == 'info':
                                state = change.val.state
                            elif change.name == 'info.state':
                                state = change.val
                            else:
                                continue

                            if not str(task) in taskList:
                                continue

                            if state == vim.TaskInfo.State.success:
                                # Remove task from taskList
                                taskList.remove(str(task))
                            elif state == vim.TaskInfo.State.error:
                                raise task.info.error
                # Move to next version
                version = update.version
        finally:
            if pcfilter:
                pcfilter.Destroy()

    def start_dumper(self, context, cmd):
        """
        Start bareos_vadp_dumper
        Parameters
        - cmd: must be "dump" or "restore"
        """
        bareos_vadp_dumper_bin = 'bareos_vadp_dumper_wrapper.sh'

        # options for bareos_vadp_dumper:
        # -S: cleanup on start
        # -D: cleanup on disconnect
        # -M: save metadata
        # -R: restore metadata
        bareos_vadp_dumper_opts = {}
        bareos_vadp_dumper_opts['dump'] = '-S -D -M'
        bareos_vadp_dumper_opts['restore'] = '-S -D -R'

        bareos_vadp_dumper_command = '%s %s %s "%s"' % (
            bareos_vadp_dumper_bin,
            bareos_vadp_dumper_opts[cmd],
            cmd,
            self.cbt_json_local_file_path)
        bareos_vadp_dumper_command_args = shlex.split(
            bareos_vadp_dumper_command)
        log_path = '/var/log/bareos'
        stderr_log_fd = tempfile.NamedTemporaryFile(dir=log_path, delete=False)

        bareos_vadp_dumper_process = None
        bareos_vadp_dumper_logfile = None
        try:
            if cmd == 'dump':
                # backup
                bareos_vadp_dumper_process = subprocess.Popen(
                    bareos_vadp_dumper_command_args,
                    bufsize=-1,
                    stdin=open("/dev/null"),
                    stdout=subprocess.PIPE,
                    stderr=stderr_log_fd,
                    close_fds=True)
            else:
                # restore
                bareos_vadp_dumper_process = subprocess.Popen(
                    bareos_vadp_dumper_command_args,
                    bufsize=-1,
                    stdin=subprocess.PIPE,
                    stdout=open("/dev/null"),
                    stderr=stderr_log_fd,
                    close_fds=True)

            # rename the stderr log file to one containing the PID
            bareos_vadp_dumper_logfile = '%s/bareos_vadp_dumper.%s.log' \
                % (log_path, bareos_vadp_dumper_process.pid)
            os.rename(stderr_log_fd.name, bareos_vadp_dumper_logfile)
            bareosfd.DebugMessage(
                context, 100,
                "start_bareos_vadp_dumper(): started %s, log stderr to %s\n" %
                (bareos_vadp_dumper_command, bareos_vadp_dumper_logfile))

        except:
            # kill children if they arent done
            if bareos_vadp_dumper_process:
                bareosfd.JobMessage(
                    context, bJobMessageType['M_WARNING'],
                    "Failed to start %s\n" %
                    (bareos_vadp_dumper_command))
                if (bareos_vadp_dumper_process is not None
                        and bareos_vadp_dumper_process.returncode is None):
                    bareosfd.JobMessage(
                        context, bJobMessageType['M_WARNING'],
                        "Killing probably stuck %s PID %s with signal 9\n" %
                        (bareos_vadp_dumper_command,
                         bareos_vadp_dumper_process.pid))
                    os.kill(bareos_vadp_dumper_process.pid, 9)
                try:
                    if bareos_vadp_dumper_process is not None:
                        bareosfd.DebugMessage(
                            context, 100,
                            "Waiting for command %s PID %s to terminate\n" %
                            (bareos_vadp_dumper_command,
                             bareos_vadp_dumper_process.pid))
                        os.waitpid(bareos_vadp_dumper_process.pid, 0)
                        bareosfd.DebugMessage(
                            context, 100,
                            "Command %s PID %s terminated\n" %
                            (bareos_vadp_dumper_command,
                             bareos_vadp_dumper_process.pid))

                except:
                    pass
                raise
            else:
                raise

        # bareos_vadp_dumper should be running now, set the process object
        # for further processing
        self.dumper_process = bareos_vadp_dumper_process

        return True

    def end_dumper(self, context):
        """
        Wait for bareos_vadp_dumper to terminate
        """
        bareos_vadp_dumper_returncode = None
        # wait up to 120s for bareos_vadp_dumper to terminate, otherwise this
        # could become an infinite loop if something goes wrong
        timeout = 120
        start_time = int(time.time())
        while self.dumper_process.poll() is None:
            if int(time.time()) - start_time > timeout:
                bareosfd.DebugMessage(
                    context, 100,
                    "Timeout wait for bareos_vadp_dumper PID %s to terminate\n" %
                    (self.dumper_process.pid))
                break

            bareosfd.DebugMessage(
                context, 100,
                "Waiting for bareos_vadp_dumper PID %s to terminate\n" %
                (self.dumper_process.pid))
            time.sleep(1)

        bareos_vadp_dumper_returncode = self.dumper_process.returncode
        self.dumper_process = None
        return bareos_vadp_dumper_returncode

    # helper functions ############

    def mkdir(self, directory_name):
        """
        Utility Function for creating directories,
        works like mkdir -p
        """
        try:
            os.stat(directory_name)
        except OSError:
            os.makedirs(directory_name)

# vim: ts=4 tabstop=4 expandtab shiftwidth=4 softtabstop=4
