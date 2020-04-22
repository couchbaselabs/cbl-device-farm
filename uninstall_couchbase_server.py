#!/usr/bin/env python3

from query_cluster import get_aws_instances, AWSState, AWSInstance
from concurrent.futures import ThreadPoolExecutor
from paramiko import SSHClient, WarningPolicy
from ssh_utils import ssh_connect, ssh_command
from argparse import ArgumentParser
from utils import ensure_min_python_version

import sys

ensure_min_python_version()


def uninstall_couchbase_server(ec2_keyname: str, server_prefix: str, region: str, ssh_keyfile: str):
    instances = list(filter(lambda x: x.name.startswith(server_prefix),
                     get_aws_instances(AWSState.RUNNING, ec2_keyname, region)))
    futures = []
    if len(instances) == 0:
        print("No instances found, nothing to do!")
        sys.exit(0)

    def _uninstall_worker(instance: AWSInstance, ssh_keyfile: str):
        ssh_client = SSHClient()
        ssh_client.load_system_host_keys()
        ssh_client.set_missing_host_key_policy(WarningPolicy())
        ssh_connect(ssh_client, instance.address, ssh_keyfile)
        exit_code = ssh_command(ssh_client, instance.address, "sudo yum erase -y couchbase-server.x86_64")
        ssh_client.close()
        return exit_code

    results = []
    with ThreadPoolExecutor(thread_name_prefix="cb_install") as tp:
        for instance in instances:
            futures.append(tp.submit(_uninstall_worker, instance, ssh_keyfile))

        for f in futures:
            results.append(f.result())

    return max(results)


if __name__ == "__main__":
    parser = ArgumentParser(prog="uninstall_couchbase_server")
    parser.add_argument("keyname", action="store", type=str,
                        help="The name of the SSH key that the EC2 instances are using")
    parser.add_argument("--region", action="store", type=str, dest="region", default="us-east-1",
                        help="The EC2 region to query (default %(default)s)")
    parser.add_argument("--server-name-prefix", action="store", type=str, dest="servername", default="couchbaseserver",
                        help="The name of the server to use to reset the Couchbase cluster (default %(default)s)")
    parser.add_argument("--ssh-key", action="store", type=str, dest="sshkey",
                        help="The key to connect to EC2 instances")
    args = parser.parse_args()

    sys.exit(uninstall_couchbase_server(args.keyname, args.servername, args.region, args.sshkey))
