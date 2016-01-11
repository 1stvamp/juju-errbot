from contextlib import contextmanager
from os import makedirs, path, walk
from shutil import chown
from subprocess import check_call

from charmhelpers import fetch
from charmhelpers.core import hookenv
from charmhelpers.core.host import adduser, add_group, lsb_release
from charmhelpers.core.templating import render
from charmhelpers.contrib.python import packages

from charms.reactive import hook


BASE_PATH = '/srv/errbot'
VAR_PATH = path.join(BASE_PATH, 'var')
LOG_PATH = path.join(VAR_PATH, 'log')
DATA_PATH = path.join(VAR_PATH, 'data')
PLUGIN_PATH = path.join(VAR_PATH, 'plugins')
ETC_PATH = path.join(BASE_PATH, 'etc')
VENV_PATH = path.join(BASE_PATH, 'venv')
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

            # Create user and group, no-op if either already exists
            add_group(p[2], system_group=True)
            adduser(p[1], shell='/bin/false', system_user=True,
                    primary_group=p[2])

            # Ensure the base path is owned appropriately
            chown(path=p[0], user=p[1], group=p[2])
            for root, dirnames, filenames in walk(path.join(p[0])):
                for f in dirnames + filenames:
                    chown(path=path.join(root, f), user=p[1], group=p[2])

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
    packages.pip_install('errbot=={}'.format(version), venv=VENV_PATH)


@hook('config-changed')
def config():
    hookenv.status_set('maintenance',
                       'Generating errbot configuration file')
    context = hookenv.config()
    context['data_path'] = DATA_PATH
    context['plugin_path'] = PLUGIN_PATH
    context['log_path'] = LOG_PATH
    with ensure_user_and_perms(PATHS):
        render(source='config.py.j2',
               target=path.join(ETC_PATH, 'config.py'),
               owner='errbot',
               perms=0o755,
               context=context)
