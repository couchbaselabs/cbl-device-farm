#!/usr/bin/env python3

from packaging.version import Version, InvalidVersion
from configure import Configuration, SettingKeyNames
from pathlib import Path
from query_cluster import get_aws_instances, AWSState, AWSInstance
from argparse import ArgumentParser
from paramiko import SSHClient, WarningPolicy
from ssh_utils import ssh_connect, sftp_upload, ssh_command
from concurrent.futures import ThreadPoolExecutor
from subprocess import PIPE, STDOUT
from typing import List
from termcolor import colored
from utils import ensure_min_python_version

import wget
import sys
import os
import subprocess
import json
import time

ensure_min_python_version()


class UnsupportedException(Exception):
    pass


class CouchbaseServerInstaller:
    __config: Configuration
    __url: str
    __version: str
    __build: str
    __raw_version: str
    __ssh_keyfile: str

    @staticmethod
    def version_to_code(version: str):
        try:
            parsed_version = Version(version)
        except InvalidVersion:
            print("Non-numeric version {} received, interpreting as codename...".format(version))
            return version

        if parsed_version >= Version("7.0"):
            return "cheshire-cat"

        print(colored("This script uses features introduced in 6.5, earlier versions not supported...", "red"))
        raise UnsupportedException("Unsupported version of Couchbase Server requested")

    @staticmethod
    def _parse_version(version: str):
        version_build = version.split("-")
        if len(version_build) == 2:
            return (CouchbaseServerInstaller._version_to_code(version_build[0]), version_build[1])

        return (version, None)

    @staticmethod
    def _generate_filename(version: str, build: str):
        if build is None:
            return "couchbase-server-enterprise-{}-centos7.x86_64.rpm".format(version)

        return "couchbase-server-enterprise-{}-{}-centos7.x86_64.rpm".format(version, build)

    def __init__(self, url: str, ssh_keyfile: str):
        self.__config = Configuration()
        self.__config.load()
        self.__raw_version = self.__config[SettingKeyNames.CBS_VERSION]
        self.__url = url
        self.__ssh_keyfile = ssh_keyfile
        (self.__version, self.__build) = CouchbaseServerInstaller._parse_version(self.__raw_version)

    def download(self):
        filename = CouchbaseServerInstaller._generate_filename(self.__version, self.__build)
        if not Path(filename).exists():
            print("Downloading Couchbase Server {}...".format(self.__raw_version))
            url = self._generate_download_url(self.__version, self.__build, filename)
            wget.download(url, filename)

    def install(self):
        filename = CouchbaseServerInstaller._generate_filename(self.__version, self.__build)
        if not Path(filename).exists():
            raise Exception("Unable to find installer, please call download first")

        print("Installing Couchbase Server to {}...".format(self.__url))
        ssh_client = SSHClient()
        ssh_client.load_system_host_keys()
        ssh_client.set_missing_host_key_policy(WarningPolicy())
        ssh_connect(ssh_client, self.__url, self.__ssh_keyfile)
        (_, stdout, _) = ssh_client.exec_command("test -f {}".format(filename))
        if stdout.channel.recv_exit_status() == 0:
            print("Install file already present on remote host, skipping upload...")
        else:
            print("Uploading file to remote host...")
            sftp = ssh_client.open_sftp()
            sftp_upload(sftp, filename, filename)
            sftp.close()

        ssh_command(ssh_client, self.__url, "sudo yum install -y {}".format(filename))
        print("Install finished!")

    def _generate_download_url(self, version: str, build: str, filename: str):
        # All access via VPN or company network
        if build is not None:
            return "http://latestbuilds.service.couchbase.com/builds/latestbuilds/couchbase-server/{}/{}/{}".format(
                   version, build, filename)

        return "http://latestbuilds.service.couchbase.com/builds/releases/{}/{}".format(version, filename)


def _run_cli_command(command: List[str], prefix: str):
    process = _start_cli_command(command)

    if prefix is None:
        for line in process.stdout:
            print(line.decode("utf-8"), end="")
    else:
        for line in process.stdout:
            print("[{}] {}".format(prefix, line.decode("utf-8")), end="")

    process.wait()
    return process.returncode


def _start_cli_command(command: List[str]):
    path = Path(os.path.dirname(__file__)).absolute() / "couchbase-cli" / "couchbase-cli"
    command.insert(0, str(path))
    return subprocess.Popen(command, stdout=PIPE, stderr=STDOUT)


def initialize_couchbase_cluster(instance: AWSInstance, username: str, password: str):
    print("Initializing {} with a new cluster...".format(instance.name))
    for i in range(5):
        retcode = _run_cli_command([
            "cluster-init",
            "-c", cluster_init_node.address,
            "--cluster-username", username,
            "--cluster-password", password,
            "--services",  "data,index,query",
            "--cluster-ramsize", "4096",
            "--cluster-index-ramsize", "1024",
            "--cluster-name", "device-farm"
        ], instance.name)

        if retcode == 0:
            break

        print(colored("Failed to initialize cluster, retrying in 2 seconds ({} attempts remaining)...".format(5 - i),
                      "yellow"))
        time.sleep(2)

    print("Setting hostname to {}...".format(instance.internal_address))
    _run_cli_command([
        "node-init",
        "-c", instance.address,
        "-u", username,
        "-p", password,
        "--node-init-hostname", instance.internal_address
    ], instance.name)


def add_server_nodes(cluster: AWSInstance, nodes: List[AWSInstance], cluster_user: str,
                     cluster_pass: str, node_user: str, node_pass: str):
    def _server_add_worker(cluster_instance: AWSInstance, server_instance: AWSInstance):
        return _run_cli_command([
            "server-add",
            "-c", cluster.address,
            "-u", cluster_user,
            "-p", cluster_pass,
            "--services",  "data,index,query",
            "--server-add", "{}:18091".format(server_instance.internal_address),
            "--server-add-username", node_user,
            "--server-add-password", node_pass
        ], server_instance.name)

    futures = []
    results = []
    with ThreadPoolExecutor(thread_name_prefix="cb_install") as tp:
        for i in instances[1:]:
            print("Adding {} as a new node to the {} cluster...".format(i.name, cluster.name))
            futures.append(tp.submit(_server_add_worker, instances[0], i))

        for f in futures:
            results.append(f.result())

    return max(results)


def rebalance_cluster(instance: AWSInstance, username: str, password: str):
    return _run_cli_command([
        "rebalance",
        "-c", instance.address,
        "-u", username,
        "-p", password
    ], instance.name)


def get_node_count(instance: AWSInstance, username: str, password: str):
    process = _start_cli_command([
        "host-list",
        "-c", instance.address,
        "-u", username,
        "-p", password,
        "-o", "json"
    ])

    process.wait()
    if process.returncode != 0:
        return 0

    result = json.loads(process.stdout.readlines()[-1])
    return len(result["nodes"])


def wait_for_healthy_nodes(instance: AWSInstance, username: str, password: str):
    NUM_ATTEMPTS = 5
    for i in range(NUM_ATTEMPTS):
        print("Checking for healthy nodes, attempt {} of {}...".format(i + 1, NUM_ATTEMPTS))
        process = _start_cli_command([
            "server-list",
            "-c", instance.address,
            "-u", username,
            "-p", password
        ])

        process.wait()
        if process.returncode != 0:
            raise Exception("Failed to get server list from cluster!")

        ready = True
        for line in process.stdout:
            if line[:2] != "ns_":
                continue

            components = line.split(' ')
            if components[2] != "healthy":
                print(colored("{} is not healthy ({})".format(components[0], components[2]), "yellow"))
                ready = False

        if ready:
            print("...All nodes healthy")
            break

        for s in range(5):
            print(".", end="")
            time.sleep(1)

        print()

    if not ready:
        raise Exception("Server nodes failed to become healthy!")


if __name__ == "__main__":
    parser = ArgumentParser(prog="install_couchbase_server")
    config = Configuration()
    config.load()

    parser.add_argument("keyname", action="store", type=str,
                        help="The name of the SSH key that the EC2 instances are using")
    parser.add_argument("--region", action="store", type=str, dest="region",
                        default=config.get(SettingKeyNames.AWS_REGION),
                        help="The EC2 region to query (default %(default)s)")
    parser.add_argument("--server-name-prefix", action="store", type=str, dest="servername",
                        default=config.get(SettingKeyNames.CBS_SERVER_PREFIX),
                        help="The name of the server to use to reset the Couchbase cluster (default %(default)s)")
    parser.add_argument("--ssh-key", action="store", type=str, dest="sshkey",
                        help="The key to connect to EC2 instances")
    parser.add_argument("--setup-only", action="store_true", dest="setuponly",
                        help="Skip the program installation, and configure only")

    args = parser.parse_args()

    futures = []
    instances = list(filter(lambda x: x.name.startswith(args.servername),
                     get_aws_instances(AWSState.RUNNING, args.keyname, args.region)))

    num_instances = len(instances)
    if num_instances == 0:
        print("No instances found, nothing to do!")
        sys.exit(0)

    if not args.setuponly:
        with ThreadPoolExecutor(thread_name_prefix="cb_install") as tp:
            for instance in instances:
                installer = CouchbaseServerInstaller(instance.address, args.sshkey)
                installer.download()  # Make sure only one does the downloading
                futures.append(tp.submit(lambda i: i.install(), installer))

            for f in futures:
                f.result()
    else:
        print("Skipping program installation, continuing to setup...")

    num_nodes = get_node_count(instances[0], "Administrator", "Couchbase123")
    if num_nodes == num_instances:
        print("Things look normal, exiting!")
        sys.exit(0)


    # Pick the first in the list to be the cluster init node
    cluster_init_node = instances[0]
    initialize_couchbase_cluster(cluster_init_node, "Administrator", "Couchbase123")

    # Add the rest to the cluster
    add_server_nodes(cluster_init_node, instances[1:], "Administrator", "Couchbase123", "Administrator", "Couchbase123")
    rebalance_cluster(cluster_init_node, "Administrator", "Couchbase123")

    wait_for_healthy_nodes(instances[0], "Administrator", "Couchbase123")
