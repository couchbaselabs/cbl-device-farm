#!/usr/bin/env python3

import boto3
import sys

from enum import Enum
from argparse import ArgumentParser
from utils import ensure_min_python_version

ensure_min_python_version()


class AWSState(Enum):
    STOPPED = 0
    RUNNING = 1

    def __str__(self):
        return self.name


class AWSInstance:
    __name: str
    __id: str
    __address: str
    __internal_address: str

    def __init__(self, name: str, id: str, address: str, internal_address: str):
        self.__name = name
        self.__id = id
        self.__address = address
        self.__internal_address = internal_address

    @property
    def name(self):
        return self.__name

    @property
    def id(self):
        return self.__id

    @property
    def address(self):
        return self.__address

    @property
    def internal_address(self):
        return self.__internal_address

    def __str__(self):
        if self.address is not None:
            return "{} ({}) @ {} ({})".format(self.name, self.id, self.address, self.internal_address)

        return "{} ({})".format(self.name, self.id)


def get_aws_instances(state: AWSState, keyName: str, region: str):
    state_code = 16
    if state == AWSState.STOPPED:
        state_code = 80

    filters = [
        {"Name": "key-name", "Values": [keyName]},
        {"Name": "instance-state-code", "Values": [str(state_code)]}
    ]
    ec2 = boto3.client("ec2", region_name=region)
    raw_output = ec2.describe_instances(Filters=filters)
    output = []

    for reservation in raw_output["Reservations"]:
        for instance in reservation["Instances"]:
            next_result = {
                "Id": instance["InstanceId"]
            }

            if state == AWSState.RUNNING:
                next_result["Address"] = instance["PublicDnsName"]
                next_result["PrivateAddress"] = instance["PrivateDnsName"]

            for tag in instance["Tags"]:
                if tag["Key"] == "Name":
                    next_result["Name"] = tag["Value"]
                    break

            output.append(AWSInstance(next_result["Name"], next_result["Id"], next_result.get("Address"),
                          next_result.get("PrivateAddress")))

    return output


if __name__ == "__main__":
    parser = ArgumentParser(prog="query_cluster")
    parser.add_argument("keyname",
                        action="store", type=str,
                        help="The name of the SSH key that the EC2 instances are using")
    parser.add_argument("state",
                        action="store", type=lambda s: AWSState[s], choices=list(AWSState),
                        help="The state of the instances to be found")
    parser.add_argument("--region",
                        action="store", type=str, dest="region", default="us-east-1",
                        help="The EC2 region to query (default %(default)s)")

    args = parser.parse_args()
    instances = get_aws_instances(args.state, args.keyname, args.region)
    if len(instances) == 0:
        print("No instances found!")
        sys.exit(0)

    print("Found the following instances:")
    for i in instances:
        print("\t{}".format(i))
