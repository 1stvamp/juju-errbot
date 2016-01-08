from functools import wraps
from glob import glob
from os import makedirs, path
from shutil import chown
from subprocess import check_call

from charmhelpers import fetch
from charmhelpers.core import hookenv
from charmhelpers.core.host import adduser, add_group, lsb_release
from charmhelpers.core.templating import render
from charmhelpers.contrib.python import packages

from charms.reactive import hook


BASE_PATH = '/srv/errbot'
VENV_PATH = path.join(BASE_PATH, 'venv')
PATHS = (
    (path.join(BASE_PATH, 'var/log'), 'errbot', 'errbot'),
    (path.join(BASE_PATH, 'var/data'), 'errbot', 'errbot'),
    (path.join(BASE_PATH, 'etc'), 'errbot', 'errbot'),
)


def apply_dir_perms(f):
    def perms():
        for p in PATHS:
            makedirs(p[0], exist_ok=True)

            # Create user and group, no-op if either already exists
            add_group(p[2], system_group=True)
            adduser(p[1], shell='/bin/false', system_user=True,
                    primary_group=p[2])

            # Ensure the base path is owned appropriately
            chown(path=p[0], user=p[1], group=p[2])
            for f in glob(path.join(p[0], '**/*')):
                chown(path=path.join(p[0], f), user=p[1], group=p[2])

    @wraps(f)
    def wrapper(*args, **kwargs):
        perms()
        ret = f(*args, **kwargs)
        perms()
        return ret

    return wrapper


@hook('config-changed')
@apply_dir_perms
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
        check_call(['/usr/bin/python3', '-m', 'venv', VENV_PATH])

    hookenv.status_set('maintenance',
                       'Installing configured version of errbot')
    version = hookenv.config('version')
    if not version:
        hookenv.log('version not set, skipping install of errbot',
                    level='WARNING')
        return

    packages.pip_install('errbot=={}'.format(version), venv=VENV_PATH)


@hook('config-changed')
@apply_dir_perms
def config():
    hookenv.status_set('maintenance',
                       'Generating errbot configuration file')
    render(source='templates/config.py.j2',
           target='/var/errbot/etc/config.py',
           owner='errbot',
           perms=0o755,
           context=hookenv.config())
