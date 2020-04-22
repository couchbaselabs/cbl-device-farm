#!/usr/bin/env python3

from couchbase.cluster import Cluster, PasswordAuthenticator
from couchbase.exceptions import BucketNotFoundError
from query_cluster import get_aws_instances, AWSState, AWSInstance
from argparse import ArgumentParser
from paramiko import SSHClient, WarningPolicy
from ssh_utils import ssh_command, ssh_connect
from install_sync_gateway import deploy_sg_config
from typing import List
from utils import ensure_min_python_version
from configure import Configuration, SettingKeyNames

ensure_min_python_version()


def reset_couchbase_cluster(cluster: Cluster, bucket_name: str):
    try:
        bucket = cluster.open_bucket(bucket_name)
        print("Flushing bucket {}...".format(bucket_name))
        bucket.flush()
    except BucketNotFoundError:
        bucket_mgr = cluster.cluster_manager()
        bucket_mgr.bucket_create(bucket_name, ram_quota=4096, flush_enabled=True, replicas=1)
        print("Created new bucket {}...".format(bucket_name))


def set_alternate_hostnames(instances: List[AWSInstance], ssh_keyfile: str, cb_user: str, cb_pass: str):
    print("Setting up external hostnames on {} nodes".format(len(instances)))
    ssh_client = SSHClient()
    ssh_client.load_system_host_keys()
    ssh_client.set_missing_host_key_policy(WarningPolicy())
    ssh_connect(ssh_client, instances[0].address, ssh_keyfile)

    format_str = ("/opt/couchbase/bin/couchbase-cli setting-alternate-address -c localhost:8091 -u {} -p {} " +
                  "--node {} --set --hostname {}")

    for i in instances:
        ssh_command(ssh_client, instances[0].name, format_str.format(cb_user, cb_pass,
                    i.internal_address, i.address))


def change_sync_gateway(url: str, ssh_keyfile: str, start: bool):
    print("Connecting to {}...".format(url))
    ssh_client = SSHClient()
    ssh_client.load_system_host_keys()
    ssh_client.set_missing_host_key_policy(WarningPolicy())
    ssh_connect(ssh_client, url, ssh_keyfile)

    if start:
        print("Starting Sync Gateway...")
        ssh_command(ssh_client, url, "sudo systemctl start sync_gateway")
    else:
        print("Stopping Sync Gateway...")
        ssh_command(ssh_client, url, "sudo systemctl stop sync_gateway")

    ssh_client.close()


if __name__ == "__main__":
    parser = ArgumentParser(prog="reset_cluster")
    config = Configuration()
    config.load()

    parser.add_argument("keyname", action="store", type=str,
                        help="The name of the SSH key that the EC2 instances are using")
    parser.add_argument("cbuser", action="store", type=str,
                        help="The user to authenticate with when resetting the server")
    parser.add_argument("cbpass", action="store", type=str,
                        help="The password to authenticate with when resetting the server")
    parser.add_argument("--region", action="store", type=str, dest="region",
                        default=config.get(SettingKeyNames.AWS_REGION),
                        help="The EC2 region to query (default %(default)s)")
    parser.add_argument("--server-name-prefix", action="store", type=str, dest="servername", default="couchbaseserver",
                        help="The prefix of the Couchbase Server nodes in EC2 (default %(default)s)")
    parser.add_argument("--bucket-name", action="store", type=str, dest="bucketname", default="device-farm-data",
                        help="The name of the bucket to reset (default %(default)s)")
    parser.add_argument("--sg-name-prefix", action="store", type=str, dest="sgname", default="syncgateway",
                        help="The prefix of the Sync Gateway instance names in EC2 (default %(default)s)")
    parser.add_argument("--ssh-key", action="store", type=str, dest="sshkey",
                        help="The key to connect to EC2 instances")

    args = parser.parse_args()
    all_instances = get_aws_instances(AWSState.RUNNING, args.keyname, args.region)
    sg_instances = list(instance for instance in all_instances
                        if args.sgname in instance.name)
    cb_instances = list(instance for instance in all_instances
                        if args.servername in instance.name)

    if len(sg_instances) == 0:
        print("No Sync Gateway instances found for the prefix {}".format(args.sgname))

    for sg in sg_instances:
        change_sync_gateway(sg.address, args.sshkey, False)

    if len(cb_instances) > 0:
        set_alternate_hostnames(cb_instances, args.sshkey, "Administrator", "Couchbase123")
        cb_cluster_url = cb_instances[0].address
        print("Connecting to couchbase://{}:8091".format(cb_cluster_url))
        cluster = Cluster("couchbase://{}:8091".format(cb_cluster_url))
        authenticator = PasswordAuthenticator(args.cbuser, args.cbpass)
        cluster.authenticate(authenticator)
        reset_couchbase_cluster(cluster, args.bucketname)
    else:
        print("No couchbase server found with the name {}".format(args.servername))

    for sg in sg_instances:
        print("Deploying updated Sync Gateway config...")
        deploy_sg_config(sg, cb_instances[0], args.sshkey)
        change_sync_gateway(sg.address, args.sshkey, True)
