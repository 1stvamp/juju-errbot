from contextlib import contextmanager
from glob import glob
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
    service_start,
    service_stop,
    user_exists,
)
from charmhelpers.core.templating import render
from charmhelpers.contrib.python.packages import pip_install

from charms.reactive import hook, set_state, when, when_file_changed


BASE_PATH = '/srv/errbot'
VAR_PATH = path.join(BASE_PATH, 'var')
LOG_PATH = path.join(VAR_PATH, 'log')
DATA_PATH = path.join(VAR_PATH, 'data')
PLUGIN_PATH = path.join(VAR_PATH, 'plugins')
ETC_PATH = path.join(BASE_PATH, 'etc')
VENV_PATH = path.join(BASE_PATH, 'venv')
CONFIG_PATH = path.join(ETC_PATH, 'config.py')
PLUGINS_CONFIG_PATH = path.join(ETC_PATH, 'plugins_config.py')
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
def install_errbot():
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
        'git',
        venv_pkg,
    ]
    fetch.apt_install(fetch.filter_installed_packages(apt_packages))

    # Make sure we have a python3 virtualenv to install into
    with ensure_user_and_perms(PATHS):
        if not path.exists(path.join(VENV_PATH, 'bin')):
            hookenv.log('Creating python3 venv')
            check_call(['/usr/bin/python3', '-m', 'venv', VENV_PATH])
            pip_install('six', venv=VENV_PATH, upgrade=True)
            # Kill system six wheel copied into venv, as it's too old
            wheels_path = path.join(path.join(VENV_PATH, 'lib'),
                                    'python-wheels')
            hookenv.log('Removing six-1.5 wheel from venv')
            six_paths = glob(path.join(wheels_path, 'six-1.5*'))
            for p in six_paths:
                check_call(['rm', '-f', path.join(wheels_path, p)])

    version = hookenv.config('version')
    if not version:
        hookenv.log('version not set, skipping install of errbot',
                    level='WARNING')
        return

    hookenv.status_set('maintenance',
                       'Installing configured version of errbot and'
                       ' dependencies')

    pip_pkgs = [
        'errbot=={}'.format(version),
    ]
    backend = hookenv.config('backend').lower()

    pip_pkg_map = {
        'irc': 'irc',
        'hipchat': 'hypchat',
        'slack': 'slackclient',
        'telegram': 'python-telegram-bot',
    }
    if backend in pip_pkg_map:
        pip_pkgs.append(pip_pkg_map[backend])

    if backend in ('xmpp', 'hipchat'):
        check_call(['/usr/bin/python3', '-m', 'venv',
                    '--system-site-packages', VENV_PATH])
        xmpp_pkgs = [
            'python3-dns',
            'python3-sleekxmpp',
            'python3-pyasn1',
            'python3-pyasn1-modules',
        ]
        fetch.apt_install(fetch.filter_installed_packages(xmpp_pkgs))

    pip_install(pip_pkgs, venv=VENV_PATH)
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
        render(source='errbot_config.py.j2',
               target=CONFIG_PATH,
               owner='errbot',
               perms=0o744,
               context=config_ctx)
        render(source='errbot_plugins_config.py.j2',
               target=PLUGINS_CONFIG_PATH,
               owner='errbot',
               perms=0o744,
               context=config_ctx)
        render(source='errbot_upstart.j2',
               target=UPSTART_PATH,
               owner='root',
               perms=0o744,
               context=upstart_ctx)

    set_state('errbot.available')


@when_file_changed([PLUGINS_CONFIG_PATH])
def configure_plugins():
    # Shutdown errbot while we configure plugins, so we don't have concurrency
    # issue with the data files being updated
    service_stop('errbot')
    errbot_path = path.join(VENV_PATH, path.join('bin', 'errbot'))
    try:
        check_call([errbot_path, '--config', CONFIG_PATH, '--restore',
                   PLUGINS_CONFIG_PATH])
    except Exception as e:
        hookenv.log('Error updating plugins: {}'.format(e),
                    level='ERROR')
    service_start('errbot')


@when('local-monitors.available', 'errbot.available')
def local_monitors(nagios):
    setup_nagios(nagios)


@when('nrpe-external-master.available', 'errbot.available')
def nrpe_external_master(nagios):
    setup_nagios(nagios)


def setup_nagios(nagios):
    hookenv.status_set('maintenance', 'Creating Nagios check')
    unit_name = hookenv.local_unit()
    nagios.add_check(['/usr/lib/nagios/plugins/check_procs',
                      '-c', '1:', '-a', 'bin/errbot'],
                     name="check_errbot_procs",
                     description="Verify at least one errbot process is "
                                 "running",
                     context=hookenv.config("nagios_context"),
                     unit=unit_name)
