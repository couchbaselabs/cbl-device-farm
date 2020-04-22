#!/usr/bin/env python3

import sys
import boto3

from argparse import ArgumentParser
from cloud_formation import gen_template
from utils import ensure_min_python_version

ensure_min_python_version()

BUCKET_NAME = "cbmobile-bucket"
BUCKET_FOLDER = "device-farm"


class ClusterConfig:
    def __init__(self, name, keyname, server_number, server_type, sync_gateway_number,
                 sync_gateway_type, region):

        self.__name = name
        self.__keyname = keyname
        self.__server_number = server_number
        self.__server_type = server_type
        self.__sync_gateway_number = sync_gateway_number
        self.__sync_gateway_type = sync_gateway_type
        self.__region = region

    @property
    def name(self):
        return self.__name

    @property
    def keyname(self):
        return self.__keyname

    @property
    def server_number(self):
        return self.__server_number

    @property
    def server_type(self):
        return self.__server_type

    @property
    def sync_gateway_number(self):
        return self.__sync_gateway_number

    @property
    def sync_gateway_type(self):
        return self.__sync_gateway_type

    @property
    def region(self):
        return self.__region

    def __validate_types(self):
        # Ec2 instances follow string format xx.xxxx
        # Hacky validation but better than nothing
        if not len(self.__server_type.split(".")) == 2:
            print("Invalid Ec2 server type")
            return False
        if not len(self.__sync_gateway_type.split(".")) == 2:
            print("Invalid Ec2 sync_gateway type")
            return False
        return True

    def __validate_numbers(self):
        # Validate to prevent accidental giant AWS cluster
        max_servers = 5
        max_sync_gateways = 10
        if self.__server_number > 5:
            print(("You have exceed your maximum number of servers: 5".format(max_servers)))
            print("Edit you limits.json file to override this behavior")
            return False
        if self.__sync_gateway_number > 10:
            print(("You have exceed your maximum number of servers: {}".format(max_sync_gateways)))
            print("Edit you limits.json file to override this behavior")
            return False
        return True

    def is_valid(self):
        if not self.__name:
            print("Make sure you provide a stackname for your cluster.")
            return False
        if not self.__keyname:
            print("Make sure you provide a keyname for you cluster")
            return False

        types_valid = self.__validate_types()
        numbers_within_limit = self.__validate_numbers()
        return types_valid and numbers_within_limit


def create_and_instantiate_cluster(config):
    print(">>> Creating cluster... ")

    print((">>> Couchbase Server Instances: {}".format(config.server_number)))
    print((">>> Couchbase Server Type:      {}".format(config.server_type)))

    print((">>> Sync Gateway Instances:     {}".format(config.sync_gateway_number)))
    print((">>> Sync Gateway Type:          {}".format(config.sync_gateway_type)))

    print(">>> Generating Cloudformation Template")
    templ_json = gen_template(config)
    print((">>> Template contents {}".format(templ_json)))

    template_file_name = "{}_cf_template.json".format(cluster_config.name)
    print((">>> Creating {} cluster on AWS".format(config.name)))

    print(("Uploading {} to s3".format(template_file_name)))
    s3 = boto3.resource("s3", region_name=config.region)
    s3.Bucket(BUCKET_NAME).put_object(Key="{}/{}".format(BUCKET_FOLDER, template_file_name), Body=templ_json)

    # Create Stack
    print(("Creating cloudformation stack: {}".format(template_file_name)))
    cf = boto3.resource("cloudformation", region_name=config.region)
    cf.create_stack(StackName=config.name, Capabilities=["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"],
                    TemplateURL="http://{}.s3.amazonaws.com/{}/{}"
                    .format(BUCKET_NAME, BUCKET_FOLDER, template_file_name),
                    Parameters=[{"ParameterKey": "KeyName", "ParameterValue": config.keyname}])


if __name__ == "__main__":
    parser = ArgumentParser(prog="create_cluster")
    parser.add_argument("stackname",
                        action="store", type=str,
                        help="name for your cluster")
    parser.add_argument("keyname", action="store", type=str,
                        help="The EC2 keyname to install on all the instances")
    parser.add_argument("--num-servers",
                        action="store", type=int, dest="num_servers", default=0,
                        help="number of couchbase server instances")

    parser.add_argument("--server-type",
                        action="store", type=str, dest="server_type", default="m3.medium",
                        help="EC2 instance type for couchbase server (default: %(default)s)")

    parser.add_argument("--num-sync-gateways",
                        action="store", type=int, dest="num_sync_gateways", default=0,
                        help="number of sync_gateway instances")

    parser.add_argument("--sync-gateway-type",
                        action="store", type=str, dest="sync_gateway_type", default="m3.medium",
                        help="EC2 instance type for sync_gateway type (default: %(default)s)")
    parser.add_argument("--region",
                        action="store", type=str, dest="region", default="us-east-1",
                        help="The AWS region to use (default: %(default)s)")

    args = parser.parse_args()

    # Creates and validates cluster configuration
    cluster_config = ClusterConfig(
        args.stackname,
        args.keyname,
        args.num_servers,
        args.server_type,
        args.num_sync_gateways,
        args.sync_gateway_type,
        args.region
    )

    if not cluster_config.is_valid():
        print("Invalid cluster configuration. Exiting...")
        sys.exit(1)

    sys.exit(0)
    create_and_instantiate_cluster(cluster_config)
