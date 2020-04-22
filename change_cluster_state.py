#!/usr/bin/env python3

import boto3
import json
import sys

from argparse import ArgumentParser
from query_cluster import get_aws_instances, AWSState, AWSInstance
from typing import List
from utils import ensure_min_python_version
from configure import Configuration, SettingKeyNames

ensure_min_python_version()


def start_cluster(aws_instances: List[AWSInstance], region: str):
    """Starts an EC2 cluster

    Arguments:
        aws_instances -- The list of instances to start, as obtained by get_aws_instances
        region        -- The region to start the instances in (e.g. us-east-1)

    Returns:
        The response from AWS
    """

    instances_ids = [x.id for x in aws_instances]
    print("Found the following stopped instances to start: {}".format(list(str(i) for i in instances)))
    ec2 = boto3.client("ec2", region_name=region)
    return ec2.start_instances(InstanceIds=instances_ids)


def stop_cluster(aws_instances: List[AWSInstance], region: str):
    """Stops an EC2 cluster

    Arguments:
        aws_instances -- The list of instances to stop, as obtained by get_aws_instances
        region        -- The region to stop the instances in (e.g. us-east-1)

    Returns:
        The response from AWS
    """

    instances_ids = [x.id for x in aws_instances]
    print("Found the following running instances to stop: {}".format(list(str(i) for i in instances)))
    ec2 = boto3.client("ec2", region_name=region)
    return ec2.stop_instances(InstanceIds=instances_ids)


if __name__ == "__main__":
    parser = ArgumentParser()
    config = Configuration()
    config.load()

    parser.add_argument("keyname", action="store", type=str,
                        help="The name of the SSH key that the EC2 instances are using")
    parser.add_argument("state", action="store", type=lambda s: AWSState[s], choices=list(AWSState),
                        help="The state to set the cluster into")
    parser.add_argument("--region",
                        action="store", type=str, dest="region", default=config.get(SettingKeyNames.AWS_REGION),
                        help="The EC2 region (default %(default)s)")

    args = parser.parse_args()
    if args.state == AWSState.STOPPED:
        instances = get_aws_instances(AWSState.RUNNING, args.keyname, args.region)
    else:
        instances = get_aws_instances(AWSState.STOPPED, args.keyname, args.region)

    if len(instances) == 0:
        print("No instances found that need changing!")
        sys.exit(0)

    if args.state == AWSState.STOPPED:
        result = stop_cluster(instances, args.region)
    else:
        result = start_cluster(instances, args.region)

    print(json.dumps(result))
