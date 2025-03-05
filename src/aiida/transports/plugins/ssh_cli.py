###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida-core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
"""Plugin for transport over SSH (and SFTP for file transfer)."""

import glob
import io
import os
import re
from stat import S_ISDIR, S_ISREG
import asyncio
import subprocess
import click

from aiida.cmdline.params import options
from aiida.cmdline.params.types.path import AbsolutePathOrEmptyParamType
from aiida.common.escaping import escape_for_bash
from aiida.common.warnings import warn_deprecation

from ..transport import BlockingTransport, TransportInternalError, TransportPath
from . import AsyncSshTransport

__all__ = ('SshCliTransport',)

OPENSSH = 'open-ssh'

class SshCliTransport(AsyncSshTransport):
    """A wrapper class on `SshTransport` that instead of depending on paramiko,
    it executes OpenSSH commands directly in a shell."""

    _valid_auth_options = (super()._valid_auth_options)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._method = OPENSSH

    async def open_async(self):
        # Do what it has to do
        self._is_open = True

        return self

    async def close_async(self):
        # Do what it has to do
        self._is_open = False


    async def copy_async(
        self,
        remotesource: TransportPath,
        remotedestination: TransportPath,
        dereference: bool = False,
        recursive: bool = True,
        preserve: bool = False,
    ):
        """Copy a file or a folder from remote to remote.

        :param remotesource: abs path to the remote source directory / file
        :param remotedestination: abs path to the remote destination directory / file
        :param dereference: follow symbolic links
        :param recursive: copy recursively
        :param preserve: preserve file attributes
            Default = False

        :type remotesource:  :class:`Path <pathlib.Path>`, :class:`PurePosixPath <pathlib.PurePosixPath>`, or `str`
        :type remotedestination:  :class:`Path <pathlib.Path>`, :class:`PurePosixPath <pathlib.PurePosixPath>`, or `str`
        :type dereference: bool
        :type recursive: bool
        :type preserve: bool

        :raises: OSError, src does not exist or if the copy execution failed.
        """

        remotesource = str(remotesource)
        remotedestination = str(remotedestination)
        if self.has_magic(remotedestination):
            raise ValueError('Pathname patterns are not allowed in the destination')

        if not remotedestination:
            raise ValueError('remotedestination must be a non empty string')
        if not remotesource:
            raise ValueError('remotesource must be a non empty string')

        options = ""
        if preserve:
            options += " -p"
        if dereference:
            options += " -L"
        if recursive:
            options += " -r"

        command = f"scp {options} {self._machine}:{remotesource} {self._machine}:{remotedestination}"
        stdout, stderr, returncode = await self.openssh_execute(command)
        if returncode != 0:
            raise OSError
        
    

    async def openssh_execute(self, command, timeout=None):
        process = await asyncio.create_subprocess_exec(
            command, 
            stdout=asyncio.subprocess.PIPE, 
            stderr=asyncio.subprocess.PIPE
        )
        if timeout is None:
            stdout, stderr = await process.communicate()
        else:
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return -1, "", "Timeout exceeded"


        return process.returncode, stdout.decode(), stderr.decode()

    
    async def async_engine(self, action: str, params: dict = {}):
        """Execute the action with the given parameters.

        :param action: the str action to execute
        :param params: the parameters for the action
        
        :return: the return code, stdout and stderr

        :raises: `TransportInternalError` if the action is not valid
        """
        bash_command = self._bash_command_str + '-c '
        
        if action in 'remove':
            command = f"ssh {self._machine} " + bash_command + f"rm {params['path']}"
            returncode, stdout, stderr = await self.openssh_execute(command)

            if returncode != 0:
                raise OSError(f"Failed to remove path: {params['path']}")
        
        if action in ['mkdir', 'makedirs']:
            command = (f"ssh {self._machine} " + bash_command +
                       f"mkdir {'-p' if action == 'makedirs' else ''} {params['path']}")
            returncode, stdout, stderr = await self.openssh_execute(command)

            if returncode != 0:
                if 'File exists' in stderr:
                    raise FileExistsError(f"Directory already exists: {params['path']}")
                else:
                    raise OSError(f"Failed to create directory: {params['path']}")

        if action == 'listdir':
            command = f"ssh {self._machine} " + bash_command + f"ls {params['path']}"
            returncode, stdout, stderr = await self.openssh_execute(command)

            return list(stdout.split())

        if action in ['isdir', 'isfile']:
            command = (f"ssh {self._machine} " + bash_command + 
                       f"test {'-d' if action == 'isdir' else '-f'} {params['path']}")
            returncode, stdout, stderr = await self.openssh_execute(command)

            return returncode == 0

        elif action == 'lstat':
            # order of stat matters
            command = f"ssh {self._machine} " + bash_command + f"stat -c '%s %u %g %a %X %Y' {params['path']}"
            returncode, stdout, stderr = await self.openssh_execute(command)

            stdout = stdout.strip()
            if not stdout:
                raise FileNotFoundError

            # order matters
            return Stat(*stdout.split())

        elif action == 'run':
            # I ignore un-used stdin and timeout, for now
            command = f"ssh {self._machine} " + params['bash_command'] + params['command']
            returncode, stdout, stderr = await self.openssh_execute(command, params['timeout'])

            return returncode, stdout, stderr

        elif action in ['put', 'puttree']:
            options = ""
            if params['preserve']:
                options += " -p"
            if params['dereference']:
                options += " -L"
            if params['recursive']:
                options += " -r"

            command = f"scp {options} {params['local_path']} {self._machine}:{params['remote_path']}"
            returncode, stdout, stderr = await self.openssh_execute(command)
            if returncode != 0:
                raise OSError

        elif action in ['get', 'gettree']:
            options = ""
            if params['preserve']:
                options += " -p"
            if params['dereference']:
                options += " -L"
            if params['recursive']:
                options += " -r"
    
            command = f"scp {options} {self._machine}:{params['remote_path']} {params['local_path']}"
            returncode, stdout, stderr = await self.openssh_execute(command)
            if returncode != 0:
                raise OSError
        else:
            raise TransportInternalError(f'Invalid action: {action}')


class Stat:
    def __init__(self, size, uid, gid, permissions, atime, mtime):
        self.st_size = size
        self.st_uid = uid
        self.st_gid = gid
        self.st_mode = permissions
        self.st_atime = atime
        self.st_mtime = mtime
