#!/usr/bin/env python3

from paramiko import SSHClient, PasswordRequiredException, SSHException, SFTPClient
from progressbar import ProgressBar
from getpass import getpass
from pathlib import Path
from utils import ensure_min_python_version

ensure_min_python_version()


def sftp_upload(sftp: SFTPClient, filename: str, remote_filename: str):
    file_size = Path(filename).stat().st_size
    progress = ProgressBar(max_value=file_size)
    sftp.put(filename, remote_filename, callback=lambda completed, total: progress.update(completed))
    progress.finish()


def ssh_connect(client: SSHClient, url: str, ssh_keyfile: str, keypass: str):
    client.connect(url, username="centos", key_filename=ssh_keyfile, passphrase=keypass)


def ssh_command(client: SSHClient, remote_name: str, command: str):
    (_, stdout, _) = client.exec_command(command, get_pty=True)
    for line in stdout:
        print("[{}] {}".format(remote_name, line), end="")

    return stdout.channel.recv_exit_status()
