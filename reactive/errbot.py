from errno import EEXIST
from os import makedirs, path
from subprocess import check_call

from charmhelpers import fetch
from charmhelpers.core import hookenv
from charmhelpers.core.host import lsb_release
from charmhelpers.contrib.python import packages

from charms.reactive import hook


VENV_PATH = '/srv/errbot/venv'


@hook('config-changed')
def install():
    hookenv.status_set('maintenance', 'Installing packages')
    codename = lsb_release()['DISTRIB_CODENAME']
    if codename == 'trusty':
        venv_pkg = 'python3.4-venv'
    elif codename == 'xenial':
        venv_pkg = 'python3.5-venv'
    else:
        venv_pkg = 'python3-venv'
    apt_packages = [
        'python3',
        'python3-pip',
        'libssl-dev',
        'libffi-dev',
        'python3-dev',
        venv_pkg,
    ]
    fetch.apt_install(fetch.filter_installed_packages(apt_packages))

    if not path.exists(path.join(VENV_PATH, 'bin')):
        base_path = path.dirname(VENV_PATH)
        try:
            makedirs(base_path)
        except OSError as e:
            if e.errno == EEXIST and path.isdir(base_path):
                pass
            else:
                raise

        check_call(['/usr/bin/python3', '-m', 'venv', VENV_PATH])

    hookenv.status_set('maintenance',
                       'Installing configured version of errbot')
    version = hookenv.config('version')
    if not version:
        hookenv.log('version not set, skipping install of errbot',
                    level='WARNING')
        return

    packages.pip_install('errbot=={}'.format(version), venv=VENV_PATH)
