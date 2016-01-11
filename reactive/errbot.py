from contextlib import contextmanager
from grp import getgrnam
from os import makedirs, path
from subprocess import check_call

from charmhelpers import fetch
from charmhelpers.core import hookenv
from charmhelpers.core.host import (
    adduser,
    add_group,
    chownr,
    lsb_release,
    restart_on_change,
    user_exists,
)
from charmhelpers.core.templating import render
from charmhelpers.contrib.python import packages

from charms.reactive import hook, set_state, when


BASE_PATH = '/srv/errbot'
VAR_PATH = path.join(BASE_PATH, 'var')
LOG_PATH = path.join(VAR_PATH, 'log')
DATA_PATH = path.join(VAR_PATH, 'data')
PLUGIN_PATH = path.join(VAR_PATH, 'plugins')
ETC_PATH = path.join(BASE_PATH, 'etc')
VENV_PATH = path.join(BASE_PATH, 'venv')
CONFIG_PATH = path.join(ETC_PATH, 'config.py')
UPSTART_PATH = '/etc/init/errbot.conf'
PATHS = (
    (VAR_PATH, 'ubunet', 'ubunet'),
    (LOG_PATH, 'errbot', 'errbot'),
    (DATA_PATH, 'errbot', 'errbot'),
    (PLUGIN_PATH, 'errbot', 'errbot'),
    (ETC_PATH, 'ubunet', 'ubunet'),
    (VENV_PATH, 'ubunet', 'ubunet'),
)


@contextmanager
def ensure_user_and_perms(paths):
    def perms():
        for p in paths:
            makedirs(p[0], exist_ok=True)

            try:
                getgrnam(p[2])
            except KeyError:
                add_group(p[2], system_group=True)

            if not user_exists(p[1]):
                adduser(p[1], shell='/bin/false', system_user=True,
                        primary_group=p[2])

            # Ensure path is owned appropriately
            chownr(path=p[0], owner=p[1], group=p[2], chowntopdir=True)

    perms()
    yield
    perms()


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

    with ensure_user_and_perms(PATHS):
        if not path.exists(path.join(VENV_PATH, 'bin')):
            check_call(['/usr/bin/python3', '-m', 'venv', VENV_PATH])

    version = hookenv.config('version')
    if not version:
        hookenv.log('version not set, skipping install of errbot',
                    level='WARNING')
        return

    hookenv.status_set('maintenance',
                       'Installing configured version of errbot')
    packages.pip_install('errbot=={}'.format(version), venv=VENV_PATH,
                         upgrade=True)
    set_state('errbot.installed')


@when('errbot.installed')
@restart_on_change({
    CONFIG_PATH: ['errbot'],
    UPSTART_PATH: ['errbot'],
}, stopstart=True)
def config():
    hookenv.status_set('maintenance',
                       'Generating errbot configuration file')

    config_ctx = hookenv.config()
    config_ctx['data_path'] = DATA_PATH
    config_ctx['plugin_path'] = PLUGIN_PATH
    config_ctx['log_path'] = LOG_PATH

    upstart_ctx = {
        'venv_path': VENV_PATH,
        'user': 'errbot',
        'group': 'errbot',
        'working_dir': BASE_PATH,
        'config_path': CONFIG_PATH,
    }

    with ensure_user_and_perms(PATHS):
        render(source='config.py.j2',
               target=CONFIG_PATH,
               owner='errbot',
               perms=0o744,
               context=config_ctx)
        render(source='errbot_upstart.j2',
               target=UPSTART_PATH,
               owner='root',
               perms=0o744,
               context=upstart_ctx)

    set_state('errbot.available')
