# Copyright 2017 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""This package pulls images from a Docker Registry.

Unlike docker_puller the format this uses is proprietary.
"""



import argparse
import logging
import sys

from containerregistry.client import docker_creds
from containerregistry.client import docker_name
from containerregistry.client.v2 import docker_image as v2_image
from containerregistry.client.v2_2 import docker_http
from containerregistry.client.v2_2 import docker_image as v2_2_image
from containerregistry.client.v2_2 import docker_image_list as image_list
from containerregistry.client.v2_2 import save
from containerregistry.client.v2_2 import v2_compat
from containerregistry.tools import logging_setup
from containerregistry.tools import patched
from containerregistry.transport import retry
from containerregistry.transport import transport_pool

import httplib2


parser = argparse.ArgumentParser(
    description='Pull images from a Docker Registry, faaaaast.')

parser.add_argument(
    '--name',
    action='store',
    help=('The name of the docker image to pull and save. '
          'Supports fully-qualified tag or digest references.'))

parser.add_argument(
    '--directory', action='store', help='Where to save the image\'s files.')

parser.add_argument(                                                                                                                                                                                                                             '--protocol', action='store', help='Protcol') 

_THREADS = 8

_PROCESSOR_ARCHITECTURE = 'amd64'

_OPERATING_SYSTEM = 'linux'


def main():
  logging_setup.DefineCommandLineArgs(parser)
  args = parser.parse_args()
  logging_setup.Init(args=args)

  if not args.name or not args.directory:
    logging.fatal('--name and --directory are required arguments.')

  if not args.protocol:
    logging.fatal('--protocol is a required argument')

  protocol = args.protocol

  if protocol !='http' and protocol !='https':
    logging.fatal('Protocol should be http or https')
  retry_factory = retry.Factory()
  retry_factory = retry_factory.WithSourceTransportCallable(httplib2.Http)
  transport = transport_pool.Http(retry_factory.Build, size=_THREADS)

  if '@' in args.name:
    name = docker_name.Digest(args.name)
  else:
    name = docker_name.Tag(args.name)

  # OCI Image Manifest is compatible with Docker Image Manifest Version 2,
  # Schema 2. We indicate support for both formats by passing both media types
  # as 'Accept' headers.
  #
  # For reference:
  #   OCI: https://github.com/opencontainers/image-spec
  #   Docker: https://docs.docker.com/registry/spec/manifest-v2-2/
  accept = docker_http.SUPPORTED_MANIFEST_MIMES

  # Resolve the appropriate credential to use based on the standard Docker
  # client logic.
  try:
    creds = docker_creds.DefaultKeychain.Resolve(name)
  # pylint: disable=broad-except
  except Exception as e:
    logging.fatal('Error resolving credentials for %s: %s', name, e)
    sys.exit(1)

  try:
    logging.info('Pulling manifest list from %r ...', name)
    with image_list.FromRegistry(name, protocol, creds, transport) as img_list:
      if img_list.exists():
        platform = image_list.Platform({
            'architecture': _PROCESSOR_ARCHITECTURE,
            'os': _OPERATING_SYSTEM,
        })
        with img_list.resolve(platform) as default_child:
          save.fast(default_child, args.directory, threads=_THREADS)
          return

    logging.info('Pulling v2.2 image from %r ...', name)
    with v2_2_image.FromRegistry(name, protocol, creds, transport, accept) as v2_2_img:
      if v2_2_img.exists():
        save.fast(v2_2_img, args.directory, threads=_THREADS)
        return

    logging.info('Pulling v2 image from %r ...', name)
    with v2_image.FromRegistry(name, creds, transport) as v2_img:
      with v2_compat.V22FromV2(v2_img) as v2_2_img:
        save.fast(v2_2_img, args.directory, threads=_THREADS)
        return
  # pylint: disable=broad-except
  except Exception as e:
    logging.fatal('Error pulling and saving image %s: %s', name, e)
    sys.exit(1)


if __name__ == '__main__':
  with patched.Httplib2():
    main()
