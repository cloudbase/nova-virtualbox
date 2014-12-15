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
Exception classes specific for the VirtualBox driver.
"""

from nova import exception
from nova import i18n


class VBoxException(exception.NovaException):
    msg_fmt = i18n._("Something went wrong: %(details)s")


class VBoxManageError(VBoxException):
    msg_fmt = i18n._("VBoxManage command %(method)s failed. "
                     "More information: %(reason)s")


class VBoxInvalid(VBoxManageError):
    msg_fmt = i18n._("Unacceptable parameters %(reason)s")


class VBoxInvalidArgument(VBoxInvalid):
    msg_fmt = i18n._("Invalid argument `%(argument)s` in "
                     "method `%(method)s`: %(reason)s")


class VBoxValueNotAllowed(VBoxInvalid):
    msg_fmt = i18n._("The value `%(value)s` for `%(argument)s` should be one "
                     "of the following: %(allowed_values)s in %(method)s.")
