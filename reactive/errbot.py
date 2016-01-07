from os import makedirs, path
from subprocess import check_call

from charmhelpers import fetch
from charmhelpers.core import hookenv
from charmhelpers.contrib.python import packages

from charms.reactive import hook


VENV_PATH = '/srv/errbot/venv'


@hook('install')
def install():
    hookenv.status_set('maintenance', 'Installing packages')
    fetch.apt_install(['python3', 'python3-pip'])

    if not path.exists(VENV_PATH):
        makedirs(path.dirname(VENV_PATH))
        check_call(['python3 -m venv', VENV_PATH])

    version = hookenv.config('version')
    packages.pip_install('errbot=={}'.format(version), venv=VENV_PATH)
