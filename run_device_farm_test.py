#!/usr/bin/env python3

import boto3
import sys

from query_cluster import get_aws_instances, AWSState
from utils import ensure_min_python_version
from argparse import ArgumentParser
from configure import Configuration, SettingKeyNames
from constants import S3_BUCKET_FOLDER, S3_BUCKET_NAME
from termcolor import colored
from enum import Enum
from tabulate import tabulate


ensure_min_python_version()


class AppType(Enum):
    IOS = "IOS_APP"
    ANDROID = "ANDROID_APP"

    def __str__(self):
        return str.lower(self.name)


def write_sync_gateway_address(keyname: str, prefix: str, region: str):
    filename = "device_farm_sg_address.txt"
    sg_address = next((i.address for i in get_aws_instances(AWSState.RUNNING, keyname, region)
                      if prefix in i.name), None)
    if sg_address is None:
        print(colored("No Sync Gateway instances found!", "red"))
        return False

    with open(filename, "w") as fout:
        fout.write(sg_address)

    print("Uploading SG address to s3")
    s3 = boto3.resource("s3", region_name=region)
    bucket = s3.Bucket(S3_BUCKET_NAME)
    key = "{}/{}".format(S3_BUCKET_FOLDER, filename)
    bucket.put_object(Key=key, Body=sg_address)
    s3_obj = bucket.Object(key)
    s3_obj.Acl().put(ACL="public-read")
    return True


def get_project_arn(project_name: str, region: str):
    df = boto3.client("devicefarm", region_name=region)
    all_projects = df.list_projects()
    if all_projects is not None and "projects" in all_projects:
        arn = next((proj["arn"] for proj in all_projects["projects"] if proj["name"] == project_name), None)

    if arn is None:
        print(colored("Project named '{}' not found!".format(project_name), "red"))

    return arn


def get_project_device_pool(project_arn: str, pool_name: str, region: str):
    df = boto3.client("devicefarm", region_name=region)
    all_pools = df.list_device_pools(arn=project_arn, type="PRIVATE")
    if all_pools is not None and "devicePools" in all_pools:
        arn = next((pool["arn"] for pool in all_pools["devicePools"] if pool["name"] == pool_name), None)

    if arn is None:
        print(colored("Device Pool named '{}' not found!".format(pool_name), "red"))

    return arn


def get_test_pacakge(project_arn: str, region: str, platform: AppType):
    if platform == AppType.IOS:
        package_type = "XCTEST_TEST_PACKAGE"
    else:
        package_type = "INSTRUMENTATION_TEST_PACKAGE"

    df = boto3.client("devicefarm", region_name=region)
    resp = df.list_uploads(arn=project_arn, type=package_type)
    if resp is None or "uploads" not in resp or len(resp.get("uploads")) == 0:
        print(colored("No test packages found in project!", "red"))
        return None

    all_uploads = resp["uploads"]
    all_uploads.sort(key=lambda u: u["created"], reverse=True)
    return all_uploads[0]["arn"]


def get_most_recent_app(project_arn: str, region: str, platform: AppType):
    df = boto3.client("devicefarm", region_name=region)
    resp = df.list_uploads(arn=project_arn, type=platform.value)
    if resp is None or "uploads" not in resp or len(resp.get("uploads")) == 0:
        print(colored("No apps found in project!", "red"))
        return None

    all_uploads = resp["uploads"]
    all_uploads.sort(key=lambda u: u["created"], reverse=True)
    return all_uploads[0]["arn"]


def schedule_test_run(project_arn: str, app_arn: str, device_pool_arn: str, test_package_arn: str,
                      platform: AppType, region: str):
    if platform == AppType.IOS:
        test_type = "XCTEST"
    else:
        test_type = "INSTRUMENTATION"

    df = boto3.client("devicefarm", region_name=region)
    resp = df.schedule_run(
        projectArn=project_arn,
        appArn=app_arn,
        devicePoolArn=device_pool_arn,
        test={
            "type": test_type,
            "testPackageArn": test_package_arn,
            "parameters": {
                "app_performance_monitoring": "false"
            }
        },
        configuration={
            "location": {
                "latitude": 37.3802418,
                "longitude": -121.9696118
            },
            "radios": {
                "wifi": True
            }
        },
        executionConfiguration={
            "jobTimeoutMinutes": 5,
            "appPackagesCleanup": True,
            "videoCapture": False
        }
    )

    print(resp)


if __name__ == "__main__":
    parser = ArgumentParser(prog="run_device_farm_test")
    config = Configuration()
    config.load()

    parser.add_argument("keyname", action="store", type=str,
                        help="The name of the SSH key that the EC2 instances are using")
    parser.add_argument("project_name", action="store", type=str,
                        help="The name of the device farm project to run")
    parser.add_argument("platform",
                        action="store", type=lambda s: AppType[str.upper(s)], choices=list(AppType),
                        help="The platform to run the test on")
    parser.add_argument("--region", action="store", type=str, dest="region",
                        default=config.get(SettingKeyNames.AWS_REGION),
                        help="The EC2 region to query (default %(default)s)")
    parser.add_argument("--sg-name-prefix", action="store", type=str, dest="sgname",
                        default=config.get(SettingKeyNames.SG_SERVER_PREFIX),
                        help="The prefix of the Sync Gateway instance names in EC2 (default %(default)s)")
    parser.add_argument("--skip-s3-upload", action="store_true", dest="skipupload",
                        help="If set, don't upload the SG address to S3")
    parser.add_argument("--ios-pool", action="store", dest="iospool",
                        default=config.get(SettingKeyNames.DEVICE_FARM_IOS_POOL),
                        help="The name of the iOS device pool to use with the project (default %(default)s)")
    parser.add_argument("--android-pool", action="store", dest="androidpool",
                        default=config.get(SettingKeyNames.DEVICE_FARM_ANDROID_POOL),
                        help="The name of the iOS device pool to use with the project (default %(default)s)")
    parser.add_argument("--dry-run", action="store_true", dest="dryrun",
                        help="Only fetch the properties needed to schedule a run, without scheduling it")
    args = parser.parse_args()

    if not args.skipupload and not args.dryrun:
        if not write_sync_gateway_address(args.keyname, args.sgname, args.region):
            sys.exit(1)

    project_arn = get_project_arn(args.project_name, "us-west-2")
    if project_arn is None:
        sys.exit(2)

    upload_arn = get_most_recent_app(project_arn, "us-west-2", args.platform)
    if upload_arn is None:
        sys.exit(3)

    if args.platform == AppType.IOS:
        device_pool_arn = get_project_device_pool(project_arn, args.iospool, "us-west-2")
    else:
        device_pool_arn = get_project_device_pool(project_arn, args.androidpool, "us-west-2")

    test_package_arn = get_test_pacakge(project_arn, "us-west-2", args.platform)

    print()
    print("Found the following components to schedule:")
    print()
    print(tabulate([["Project", project_arn], ["App", upload_arn], ["Device Pool", device_pool_arn], 
                   ["Test Package", test_package_arn]], ["Component", "ARN"]))
    print()

    if args.dryrun:
        print("Dry run specified, exiting...")
        sys.exit(0)

    schedule_test_run(project_arn, upload_arn, device_pool_arn, test_package_arn, args.platform, "us-west-2")
