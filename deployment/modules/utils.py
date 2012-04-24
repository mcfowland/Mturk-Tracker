import os
from os.path import join as pjoin

from pprint import pprint
from fabric import colors
from fabric.api import run, sudo, hide, settings, put, env, prefix, cd
from fabric.contrib.files import upload_template


PROPER_SUDO_PREFIX = "sudo -i -S -p '%s' "


def show(msg, *args):
    "Print some message with increased visibility."
    print colors.cyan('==>', bold=True), msg % args


def cget(name):
    u"Get configuration variable from the global context."
    return env["ctx"].get(name)


def cset(name, value, force=False):
    u"Save configuration variable to the global context, if it's not defined."
    if force:
        env["ctx"]["name"] = value
    else:
        value = env["ctx"].setdefault(name, value)
    return value


def print_context():
    show("Current configuration ")
    pprint(dict((k, v) for k, v in env["ctx"].items() if v is not None))
    show("Working on: %s" % colors.green(env["host"]))
    show("Deploying to instance: %s" % colors.green(cget("instance")))


def local_files_dir(subpath=""):
    """Returns the absolute path of deployment assets (`files` directory).
    This is a *local* path. It is used before code fetch is done
    on the remote machine.
    """
    this_dir = os.path.dirname(os.path.abspath(__file__))
    deployment_dir = os.path.abspath(pjoin(this_dir, os.path.pardir))
    path = pjoin(deployment_dir, "files")
    if subpath:
        path = pjoin(path, subpath)
    return path


def remote_files_dir(subpath=""):
    """Returns the absolute path of deployment assets (`files` directory).
    This is a *remote* path. It is used after code fetch is done
    on the remote machine.
    """
    path = cget("deployment_files")
    if subpath:
        path = pjoin(path, subpath)
    return path


def get_permissions(path, use_sudo=False):
    command = use_sudo and sudo or run
    with settings(hide("running", "stdout")):
        result = command('stat --printf "%%a %%U %%G" %s' % path)
    mode, user, group = result.split()
    return mode, user, group


def ensure_permissions(path, mode=None, user=None, group=None):
    current = get_permissions(path, use_sudo=True)
    if mode is not None and current[0] != mode:
        with settings(hide("running", "stdout")):
            sudo("chmod %s %s" % (str(mode), path))
    if user is not None and current[1] != user:
        with settings(hide("running", "stdout")):
            sudo("chown %s %s" % (user, path))
    if group is not None and current[2] != group:
        with settings(hide("running", "stdout")):
            sudo("chown :%s %s" % (group, path))


def put_file_with_perms(local, remote, mode=None, user=None, group=None):
    with settings(hide("running")):
        put(local, remote, use_sudo=True)
    ensure_permissions(remote, mode, user, group)


def create_dir_with_perms(path, mode=None, user=None, group=None):
    with settings(hide("running")):
        sudo("mkdir -p %s" % path)
    ensure_permissions(path, mode, user, group)


def upload_template_with_perms(source, destination, context=None, mode=None,
        user=None, group=None):
    with settings(hide("stdout", "running")):
        upload_template(source, destination, context=context, use_sudo=True,
            backup=False)
    ensure_permissions(destination, mode=mode, user=user, group=group)


def dir_exists(location):
    """Tells if there is a remote directory at the given location."""
    with settings(hide("running", "stdout")):
        res = run("test -d '%s' && echo OK ; true" % (location)).endswith("OK")
    return res


def run_django_cmd(command, args=""):
    ve_dir = cget("virtualenv_dir")
    show("Running django command: %s with args %s", command, args)
    with prefix('source %s' % pjoin(ve_dir, "bin", "activate")):
        with cd(cget("manage_py_dir")):
            with settings(hide("stdout", "running"),
                    sudo_prefix=PROPER_SUDO_PREFIX):
                sudo("DJANGO_SETTINGS_MODULE=%s python manage.py %s %s" % (
                    cget("settings_full_name"), command, args),
                    user=cget("user"))


def get_boolean(value):
        return bool(value in [True, 1, 'True', 'true', '1', 'T', 't'])


def install_without_prompt(packages, description, silent=True):
    """Installs given packages with no prompt and output.
    Parameters:
        packages - a string of space-separated package names.
    """
    show(colors.yellow("Installing {0}.").format(description))
    with settings(sudo_prefix=PROPER_SUDO_PREFIX):
        sudo("apt-get install -y{silent} {packages}".format(
            packages=packages, silent=' -q' if silent else ''))


def create_target_directories(dirs, perms, user):
    """Creates all directories in the list."""
    for name in dirs:
        if not dir_exists(name):
            show(colors.yellow("Creating missing directory: %s"), name)
            create_dir_with_perms(name, perms, user, user)