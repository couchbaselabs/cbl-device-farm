#!/usr/bin/env python3

from configure import Configuration, SettingKeyNames
from pathlib import Path
from paramiko import SSHClient, WarningPolicy
from ssh_utils import ssh_connect, ssh_command, sftp_upload
from argparse import ArgumentParser
from query_cluster import get_aws_instances, AWSState, AWSInstance
from concurrent.futures import ThreadPoolExecutor
from utils import ensure_min_python_version

import wget
import sys
import json

ensure_min_python_version()


class SyncGatewayInstaller:
    __config: Configuration
    __url: str
    __version: str
    __build: str
    __raw_version: str
    __ssh_keyfile: str

    @staticmethod
    def _parse_version(version: str):
        version_build = version.split("-")
        if len(version_build) == 2:
            return (version_build[0], version_build[1])

        return (version, None)

    @staticmethod
    def _generate_filename(version: str, build: str):
        if build is None:
            return "couchbase-sync-gateway-enterprise_{}_x86_64.rpm".format(version)

        return "couchbase-sync-gateway-enterprise_{}-{}_x86_64.rpm".format(version, build)

    def __init__(self, url: str, ssh_keyfile: str):
        self.__config = Configuration()
        self.__config.load()
        self.__raw_version = self.__config[SettingKeyNames.SG_VERSION]
        self.__url = url
        self.__ssh_keyfile = ssh_keyfile
        (self.__version, self.__build) = SyncGatewayInstaller._parse_version(self.__raw_version)

    def install(self):
        filename = SyncGatewayInstaller._generate_filename(self.__version, self.__build)
        if not Path(filename).exists():
            print("Downloading Sync Gateway {}...".format(self.__raw_version))
            url = self._generate_download_url(self.__version, self.__build, filename)
            wget.download(url, filename)

        print("Installing Sync Gateway to {}...".format(self.__url))
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
            return "http://latestbuilds.service.couchbase.com/builds/latestbuilds/sync_gateway{}/{}/{}".format(
                   version, build, filename)

        return "http://latestbuilds.service.couchbase.com/builds/releases/mobile/couchbase-sync-gateway/{}/{}".format(
                version, filename)


def deploy_sg_config(instance: AWSInstance, cb_node: AWSInstance, ssh_keyfile: str):
    template = {
        "logging": {
            "log_file_path": "/var/tmp/sglogs",
            "console": {
                "enabled": False
            },
            "debug": {
                "enabled": True
            }
        },
        "databases": {
            "db": {
                "server": "couchbase://{}".format(cb_node.address),
                "username": "sg",
                "password": "letmein",
                "bucket": "device-farm-data",
                "users": {"GUEST": {"disabled": False, "admin_channels": ["*"]}},
                "allow_conflicts": False,
                "revs_limit": 20
            }
        },
        "interface": "0.0.0.0:4984",
        "adminInterface": "{}:4985".format(instance.internal_address)
    }

    config_filename = "{}_config.json".format(instance.name)
    with open(config_filename, "w") as fout:
        json.dump(template, fout)

    ssh_client = SSHClient()
    ssh_client.load_system_host_keys()
    ssh_client.set_missing_host_key_policy(WarningPolicy())
    ssh_connect(ssh_client, instance.address, ssh_keyfile)
    ssh_command(ssh_client, instance.name, "sudo systemctl stop sync_gateway")

    sftp = ssh_client.open_sftp()
    sftp_upload(sftp, config_filename, config_filename)
    sftp.close()

    command = """
              sudo chown sync_gateway {0};
              sudo mv {0} /home/sync_gateway/sync_gateway.json;
              sudo systemctl start sync_gateway
              """.format(config_filename)
    ssh_command(ssh_client, instance.name, command)
    ssh_client.close()


if __name__ == "__main__":
    parser = ArgumentParser(prog="install_sync_gateway")
    config = Configuration()
    config.load()

    parser.add_argument("keyname", action="store", type=str,
                        help="The name of the SSH key that the EC2 instances are using")
    parser.add_argument("--region", action="store", type=str, dest="region",
                        default=config.get(SettingKeyNames.AWS_REGION),
                        help="The EC2 region to query (default %(default)s)")
    parser.add_argument("--server-name-prefix", action="store", type=str, dest="servername", default="couchbaseserver",
                        help="The prefix of the server(s) to use for Couchbase Server (default %(default)s)")
    parser.add_argument("--sg-name-prefix", action="store", type=str, dest="sgname", default="syncgateway",
                        help="The prefix of the server(s) to use for Sync Gateway (default %(default)s)")
    parser.add_argument("--ssh-key", action="store", type=str, dest="sshkey",
                        help="The key to connect to EC2 instances")
    parser.add_argument("--setup-only", action="store_true", dest="setuponly",
                        help="Skip the program installation, and configure only")

    args = parser.parse_args()

    def _install_worker(instance: AWSInstance, ssh_keyfile: str):
        installer = SyncGatewayInstaller(instance.address, ssh_keyfile)
        installer.install()

    futures = []
    instances = get_aws_instances(AWSState.RUNNING, args.keyname, args.region)
    sg_instances = list(filter(lambda x: x.name.startswith(args.sgname), instances))

    if len(sg_instances) == 0:
        print("No instances found, nothing to do!")
        sys.exit(0)

    if not args.setuponly:
        with ThreadPoolExecutor(thread_name_prefix="sg_install") as tp:
            for instance in sg_instances:
                futures.append(tp.submit(_install_worker, instance, args.sshkey))

            for f in futures:
                f.result()
    else:
        print("Skipping program installation, continuing to setup...")

    cb_node = next(i for i in instances if i.name.startswith(args.servername))
    futures = []
    with ThreadPoolExecutor(thread_name_prefix="sg_install") as tp:
        for instance in sg_instances:
            futures.append(tp.submit(deploy_sg_config, instance, cb_node, args.sshkey))

        for f in futures:
            f.result()
