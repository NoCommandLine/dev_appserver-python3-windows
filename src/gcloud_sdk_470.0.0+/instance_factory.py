#!/usr/bin/env python
#
# Copyright 2007 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Includes modifications by NoCommandLine (info@nocommandline.com | https://nocommandline.com)
# to allow support for Python 3 Apps on Windows
"""Serves content for "script" handlers using the Python runtime."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function



import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time

import google
from google.appengine._internal import six

# pylint: disable=g-import-not-at-top
if six.PY2:
  from google.appengine.api import appinfo
else:
  from google.appengine.api import appinfo

from google.appengine.tools.devappserver2 import application_configuration
from google.appengine.tools.devappserver2 import errors
from google.appengine.tools.devappserver2 import http_runtime
from google.appengine.tools.devappserver2 import instance

_MODERN_DEFAULT_ENTRYPOINT = 'gunicorn -b :${PORT} main:app'

_DEFAULT_REQUIREMENT_FILE_NAME = 'requirements.txt'

_RECREATE_MODERN_INSTANCE_FACTORY_CONFIG_CHANGES = frozenset([
    application_configuration.ENTRYPOINT_ADDED,
    application_configuration.ENTRYPOINT_REMOVED,
])

_MODERN_REQUEST_ID_HEADER_NAME = 'X-Appengine-Api-Ticket'


# TODO: Refactor this factory class for modern runtimes.
class PythonRuntimeInstanceFactory(instance.InstanceFactory,
                                   instance.ModernInstanceFactoryMixin):
  """A factory that creates new Python runtime Instances.

  This InstanceFactory supports 3 use cases:
  o Running the python27 runtime as separate module with a __main__ method
    (default).
  o Running the python27 runtime as an executable.
  o Running the python3 runtime as an executable.

  When running the python27 runtime as a module with a __main__ method, this
  InstanceFactory creates a separate python27 interpreter process:
   - Defaults to running the python interpreter running this code,
     (running the devappserver, See _python27_executable_path). To use a
      different python interpreter call SetPython27ExecutablePath.
   - Defaults to a runtime module packaged with the SDK (See
     _python27_runtime_path). To use a different runtime module call
     SetPython27RuntimePath with the path to the module..

  When running the python27 runtime as an executable this InstanceFactory
  creates a separate process running the executable. To enable this case:
    - Call SetPython27RuntimeIsExecutable(True)
    - Call SetPython27RuntimePath with the path to the executable.

  When running the python3 runtime as an executable the behavior is
  specified in the applications configuration (app.yaml file.).
  """
  START_URL_MAP = appinfo.URLMap(
      url='/_ah/start',
      script='$PYTHON_LIB/default_start_handler.py',
      login='admin')
  WARMUP_URL_MAP = appinfo.URLMap(
      url='/_ah/warmup',
      script='$PYTHON_LIB/default_warmup_handler.py',
      login='admin')
  SUPPORTS_INTERACTIVE_REQUESTS = True
  FILE_CHANGE_INSTANCE_RESTART_POLICY = instance.AFTER_FIRST_REQUEST

  _runtime_python_path = {}
  _virtualenv_python_path = None

  @classmethod
  def SetVirtualEnvPythonPath(cls, virtualenv_python_path):
    """Set the virtual env directory controlled by the user via flag."""
    PythonRuntimeInstanceFactory._virtualenv_python_path = (
        virtualenv_python_path
    )
    if not os.path.exists(virtualenv_python_path):
      os.makedirs(virtualenv_python_path)

  @classmethod
  def SetRuntimePythonPath(cls, runtime_python_path):
    """Set the per runtime path to the Python interpreter."""
    PythonRuntimeInstanceFactory._runtime_python_path = runtime_python_path

  def _GetPythonInterpreterPath(self):
    """Returns the python interpreter path for the current runtime."""
    runtime = self._module_configuration.runtime
    runtime_python_path = PythonRuntimeInstanceFactory._runtime_python_path
    if runtime_python_path and isinstance(runtime_python_path, str):
      return runtime_python_path
    elif runtime_python_path and runtime in runtime_python_path:
      return runtime_python_path[runtime]
    elif hasattr(sys, 'executable') and sys.executable:
      return sys.executable
    else:
      return 'python' if hasattr(sys, 'getwindowsversion') else 'python3'

  def _CheckPythonExecutable(self):
    python_interpreter_path = self._GetPythonInterpreterPath()
    try:
      version_str = subprocess.check_output(
          [python_interpreter_path, '--version'])
      logging.info(
          'Detected python version "%s" for runtime "%s" at "%s".',
          version_str,
          self._module_configuration.runtime,
          python_interpreter_path)
    except OSError:  # If python is not found, an OSError would be raised.
      raise errors.Python3NotFoundError(
          'Could not a python executable at "%s". Please verify that your '
          'python installation, PATH and --runtime_python_path are correct.'
          % python_interpreter_path)

  def __init__(self, request_data, runtime_config_getter, module_configuration):
    """Initializer for PythonRuntimeInstanceFactory.

    Args:
      request_data: A wsgi_request_info.WSGIRequestInfo that will be provided
          with request information for use by API stubs.
      runtime_config_getter: A function that can be called without arguments
          and returns the runtime_config_pb2.Config containing the configuration
          for the runtime.
      module_configuration: An application_configuration.ModuleConfiguration
          instance respresenting the configuration of the module that owns the
          runtime.
    """
    super(PythonRuntimeInstanceFactory, self).__init__(
        request_data,
        8 if runtime_config_getter().threadsafe else 1, 10)
    self._runtime_config_getter = runtime_config_getter
    self._module_configuration = module_configuration
    self._venv_dir = ''
    self._CheckPythonExecutable()
    self._SetupVirtualenvFromConfiguration()

  def __del__(self):
    self._CleanUpVenv(self._venv_dir)

  def _CleanUpVenv(self, venv_dir):
    # Delete it only if it is not user provided
    virtualenv_python_path = (
        PythonRuntimeInstanceFactory._virtualenv_python_path
    )
    if virtualenv_python_path is not None:
      if os.path.exists(venv_dir):
        shutil.rmtree(venv_dir)

  @property
  def _OrigRequirementsFile(self):
    return os.path.join(
        os.path.dirname(self._module_configuration.config_path),
        _DEFAULT_REQUIREMENT_FILE_NAME)

  @property
  def _entrypoint(self):
    """Returns the entrypoint as is in module configuration."""
    
    # Changes by NoCommandLine - If app.yaml contains an entrypoint, dev_appserver.py prepends it with 'exec'
    # However, trying to run 'exec' via subprocess.Popen on Windows leads to the error - 'exec' is not recognized as an internal or external command
    # So, if we're on Windows, we'll strip the 'exec' from entrypoint and just run the original string supplied by the user based on the assumption
    # that the string starts with an actual executable program which will be in the Scripts folder
    if (self._is_windows() and self._module_configuration.entrypoint):
      import re
      return re.sub('^exec[\s]+' , '', self._module_configuration.entrypoint)
    
    return self._module_configuration.entrypoint

  def _SetupVirtualenvFromConfiguration(self):
    self._CleanUpVenv(self._venv_dir)
    # Create one only if it is not user provided
    virtualenv_python_path = (
        PythonRuntimeInstanceFactory._virtualenv_python_path
    )
    if virtualenv_python_path is None:
      self._venv_dir = tempfile.mkdtemp()
    else:
      self._venv_dir = os.path.join(
          virtualenv_python_path, self._module_configuration.module_name
      )
      if not os.path.exists(self._venv_dir):
        os.makedirs(self._venv_dir)

    if self._entrypoint:
      self.venv_env_vars = self._SetupVirtualenv(
          self._venv_dir, self._OrigRequirementsFile)
    else:  # use default entrypoint
      # Changes by NoCommandLine
      # For windows, pass self._OrigRequirementsFile because in Windows, the temporary file created as requirements_file (see else clause below) isn't accessible
      if (self._is_windows()):
        self.venv_env_vars = self._SetupVirtualenv(
            self._venv_dir, self._OrigRequirementsFile)
      else:
        # Copy requirements.txt into a temporary file. It will be destroyed once
        # the life of self._requirements_file ends. It is created in a directory
        # different from venv_dir so that venv_dir starts clean.
        with tempfile.NamedTemporaryFile() as requirements_file:
          # Make a copy of user requirements.txt, the copy is safe to modify.
          if os.path.exists(self._OrigRequirementsFile):
            with open(self._OrigRequirementsFile, 'rb') as orig_f:
              requirements_file.write(orig_f.read())

          # Similar to production, append gunicorn to requirements.txt
          # as default entrypoint needs it.
          requirements_file.write(six.b('\ngunicorn'))

          # flushing it because _SetupVirtualenv uses it in a separate process.
          requirements_file.flush()
          self.venv_env_vars = self._SetupVirtualenv(
              self._venv_dir, requirements_file.name)

  def configuration_changed(self, config_changes):
    """Called when the configuration of the module has changed.

    Args:
      config_changes: A set containing the changes that occoured. See the
          *_CHANGED constants in the application_configuration module.
    """
    if config_changes & _RECREATE_MODERN_INSTANCE_FACTORY_CONFIG_CHANGES:
      self._SetupVirtualenvFromConfiguration()

  def dependency_libraries_changed(self, file_changes):
    """Decide whether dependency libraries in requirements.txt changed.

    If these libraries changed, recreate virtualenv with updated
    requirements.txt. This should only be called for python3+ runtime.

    Args:
      file_changes: A set of strings, representing paths to file changes.

    Returns:
      A bool indicating whether dependency libraries changed.
    """
    dep_libs_changed = next(
        (
            x
            for x in file_changes
            if six.ensure_str(x).endswith(_DEFAULT_REQUIREMENT_FILE_NAME)
        ),
        None,
    )
    if dep_libs_changed:
      self._SetupVirtualenvFromConfiguration()
    return dep_libs_changed is not None

  def _GetRuntimeArgs(self):
    # Changes by NoCommandLine to support Windows platform
    if self._is_windows():
      return (self._entrypoint or 'waitress-serve --listen=*:${PORT} main:app').split()

    return (self._entrypoint or _MODERN_DEFAULT_ENTRYPOINT).split()

  @classmethod
  def _WaitForProcWithLastLineStreamed(cls, proc, proc_stdout):
    # Stream the last line of a process output, so that users can see
    # progress instead of doubting dev_appserver hangs.
    while proc.poll() is None:  # in progress
      lastline = proc_stdout.readline().strip()
      if lastline:
        sys.stdout.write(lastline)
        sys.stdout.flush()
        # Erase previous lastline.
        w = len(lastline)
        sys.stdout.write(six.ensure_str('\b' * w + ' ' * w + '\b' * w))
        time.sleep(0.2)
    sys.stdout.write('\n')
    return proc.poll()

  def _is_windows(self):
    return hasattr(sys, 'getwindowsversion')

  def _RunPipInstall(self, venv_dir, requirements_file_name):
    """Run pip install inside a virtualenv, with decent stdout."""
    # Run pip install based on user supplied requirements.txt.
    pip_out = tempfile.NamedTemporaryFile(delete=False)
    logging.info(
        'Using pip to install dependency libraries; pip stdout is redirected '
        'to %s', pip_out.name)

    with open(pip_out.name, 'r') as pip_out_r:
      venv_bin = os.path.join(venv_dir, 'bin')
      if self._is_windows():
        # On Windows, the virtual env directory is Scripts.
        venv_bin = os.path.join(venv_dir, 'Scripts')
      pip_path = os.path.join(venv_bin, 'pip')

      pip_env = os.environ.copy()
      pip_env.update({
          'VIRTUAL_ENV': venv_dir,
          'PATH': os.pathsep.join([venv_bin, os.environ['PATH']]),
      })
      # Changes by NoCommandLine. See NOTE_PIP_USER below
      """
        NOTE_PIP_USER 
        Running pip install on Windows gives the error: [WinError 5] Access is denied:   Consider using the `--user` option or check the permissions.
      
        If you then use the --user option, you get another error: Can not perform a '--user' install. User site-packages are not visible in this virtualenv.
        The solution to this second problem is to set include-system-site-packages to true when creating the virtual env
      
        Setting the environment var 'PIP_USER = False' solves the above two problems (source - https://github.com/gitpod-io/gitpod/issues/1997#issuecomment-708480259)
        Note that we used 'false' which is a string instead of False the boolean value because all environment variables and values have to be string
      """
      if(self._is_windows()):
        pip_env['PIP_USER'] = 'false'

      if self._module_configuration.build_env_variables:
        pip_env.update(self._module_configuration.build_env_variables)

      pip_upgrade = (
          ['python', '-m', 'pip', 'install', '--upgrade', 'pip']
          if self._is_windows()
          else [pip_path, 'install', '--upgrade', 'pip']
      )
      # Changes by NoCommandLine.
      pip_cmds = [
                pip_upgrade,
                [pip_path, 'install', '-r', requirements_file_name],
                ]
      if self._is_windows():
          pip_cmds.append([pip_path, 'install',  'waitress'])
          
      for pip_cmd in pip_cmds: # End of Changes by NoCommandLine
        cmd_str = ' '.join(pip_cmd)
        logging.info('Running %s', cmd_str)
        pip_proc = subprocess.Popen(pip_cmd, stdout=pip_out, env=pip_env)
        if PythonRuntimeInstanceFactory._WaitForProcWithLastLineStreamed(
            pip_proc, pip_out_r) != 0:
          sys.exit('Failed to run "{}"'.format(cmd_str))

  def _SetupVirtualenv(self, venv_dir, requirements_file_name):
    """Create virtualenv for py3 instances and run pip install."""
    # Create a clean virtualenv
    # TODO: Return this to python3, maybe use a flag for python3
    
    # Changes by NoCommandLine
    """
    On Windows, an error is raised when you try to create a virtualenv in a folder
    which already has a virtualenv. You get a 'Permission Denied to the <python file>'
    in that virtualenv' error.

    Workaround will be  if
      a) this is windows 
      b) and a venv exists
      c) and python exists in it (this is our way of confirming it isn't an empty virtualenv)
    then skip trying to recreate the virtualenv
    """
    if(
        self._is_windows() and 
        os.path.exists(venv_dir) and
        os.path.exists(os.path.join(os.path.join(venv_dir, 'Scripts'), 'python.exe'))
      ):
        self._RunPipInstall(venv_dir, requirements_file_name)
        
    else: # end of changes by NoCommandLine
      args = [self._GetPythonInterpreterPath(), '-m', 'venv', venv_dir]
      call_res = subprocess.call(args)
      if call_res:
        # `python3 -m venv` Failed.
        # Clean up venv_dir and try 'virtualenv' command instead.
        self._CleanUpVenv(venv_dir)
        fallback_args = ['virtualenv', venv_dir]
        logging.warning(
            'Failed creating virtualenv with "%s", \n'
            'trying "%s"', ' '.join(args), ' '.join(fallback_args))
        call_res = subprocess.call(fallback_args)
        if call_res:
          raise IOError('Cannot create virtualenv {}'.format(venv_dir))
        logging.warning(
            'Runtime python interpreter will be selected by virtualenv')
      self._RunPipInstall(venv_dir, requirements_file_name)

    # These env vars are used in subprocess to have the same effect as running
    # `source ${venv_dir}/bin/activate`
    if self._is_windows():
      return {
          'VIRTUAL_ENV': venv_dir,
          'PATH': ';'.join(
              [os.path.join(venv_dir, 'Scripts'), os.environ['PATH']]
          ),
      }
    else:
      return {
          'VIRTUAL_ENV': venv_dir,
          'PATH': ':'.join([os.path.join(venv_dir, 'bin'), os.environ['PATH']]),
      }

  def _GetRuntimeEnvironmentVariables(self, instance_id=None):
    my_runtime_config = self._runtime_config_getter()
    res = {'PYTHONHASHSEED': 'random'}
    res.update(self.get_modern_env_vars(instance_id))
    res.update(self.venv_env_vars)
    res['API_HOST'] = my_runtime_config.api_host
    res['API_PORT'] = str(my_runtime_config.api_port)
    res['GAE_APPLICATION'] = six.ensure_str(my_runtime_config.app_id)

    for kv in my_runtime_config.environ:
      res[kv.key] = kv.value
    return res

  def _get_process_flavor(self):
    return http_runtime.START_PROCESS_WITH_ENTRYPOINT

  def new_instance(self, instance_id, expect_ready_request=False):
    """Create and return a new Instance.

    Args:
      instance_id: A string or integer representing the unique (per module) id
          of the instance.
      expect_ready_request: If True then the instance will be sent a special
          request (i.e. /_ah/warmup or /_ah/start) before it can handle external
          requests.

    Returns:
      The newly created instance.Instance.
    """
    def instance_config_getter():
      runtime_config = self._runtime_config_getter()
      runtime_config.instance_id = str(instance_id)
      return runtime_config

    proxy = http_runtime.HttpRuntimeProxy(
        self._GetRuntimeArgs(),
        instance_config_getter,
        self._module_configuration,
        env=self._GetRuntimeEnvironmentVariables(instance_id),
        start_process_flavor=self._get_process_flavor(),
        request_id_header_name=_MODERN_REQUEST_ID_HEADER_NAME,
    )
    return instance.Instance(self.request_data,
                             instance_id,
                             proxy,
                             self.max_concurrent_requests,
                             self.max_background_threads,
                             expect_ready_request)
