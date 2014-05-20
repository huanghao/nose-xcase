#!/usr/bin/env python
from setuptools import setup

from itest import __version__

setup(name='itest',
      version=__version__,
      description='Functional test framework',
      long_description='Functional test framework',
      license='GPLv2',
      platforms=['Linux'],
      include_package_data=True,
      packages=['itest', 'itest.conf', 'imgdiff', 'spm', 'nosexcase'],
      package_data={'': ['*.html']},
      data_files=[('/etc', ['spm/spm.yml'])],
      entry_points={
          'nose.plugins.0.10': [
              'xcase = nosexcase.xcase:XCase'
              ]
          },
      scripts=[
          'scripts/runtest',
          'scripts/imgdiff',
          'scripts/spm',
          ],
      classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Environment :: Console',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
          'Operating System :: POSIX :: Linux',
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.7',
          'Topic :: Software Development :: Testing',
          ],
      )
