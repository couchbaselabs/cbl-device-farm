#!/usr/bin/env python3

from troposphere import Ref, Template, Parameter, Tags
from utils import ensure_min_python_version

import troposphere.ec2 as ec2

ensure_min_python_version()


def gen_template(config) -> dict:
    """Generates a Cloud Formation template to make a device stack on EC2 based on the passed configuration

    Arguments:
        config -- The configuration to use when generating the template
                  (specifies things like number of server instances, etc)

    Returns:
        The generated template as a JSON object
    """

    num_couchbase_servers = config.server_number
    couchbase_instance_type = config.server_type

    num_sync_gateway_servers = config.sync_gateway_number
    sync_gateway_server_type = config.sync_gateway_type

    t = Template()
    t.set_description(
        'An Ec2-classic stack with Couchbase Server + Sync Gateway'
    )

    def createCouchbaseSecurityGroups(t):

        # Couchbase security group
        secGrpCouchbase = ec2.SecurityGroup('CouchbaseSecurityGroup')
        secGrpCouchbase.GroupDescription = "Allow access to Couchbase Server"
        secGrpCouchbase.SecurityGroupIngress = [
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="22",
                ToPort="22",
                CidrIp="0.0.0.0/0",
            ),
            # Sync Gatway Ports
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="4984",
                ToPort="4985",
                CidrIp="0.0.0.0/0",
            ),
            ec2.SecurityGroupRule(   # expvars
                IpProtocol="tcp",
                FromPort="9876",
                ToPort="9876",
                CidrIp="0.0.0.0/0",
            ),
            # Couchbase Server Client-To-Node Ports
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="8091",
                ToPort="8096",
                CidrIp="0.0.0.0/0",
            ),
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="11207",
                ToPort="11207",
                CidrIp="0.0.0.0/0",
            ),
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="11210",
                ToPort="11211",
                CidrIp="0.0.0.0/0",
            ),
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="18091",
                ToPort="18096",
                CidrIp="0.0.0.0/0",
            ),
            # Couchbase Server Node-To-Node Ports
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="4369",
                ToPort="4369",
                CidrIp="172.31.0.0/16",
            ),
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="9100",
                ToPort="9105",
                CidrIp="172.31.0.0/16",
            ),
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="9110",
                ToPort="9118",
                CidrIp="172.31.0.0/16",
            ),
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="9120",
                ToPort="9122",
                CidrIp="172.31.0.0/16",
            ),
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="9130",
                ToPort="9130",
                CidrIp="172.31.0.0/16",
            ),
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="9999",
                ToPort="9999",
                CidrIp="172.31.0.0/16",
            ),
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="11209",
                ToPort="11210",
                CidrIp="172.31.0.0/16",
            ),
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="19130",
                ToPort="19130",
                CidrIp="172.31.0.0/16",
            ),
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="21100",
                ToPort="21100",
                CidrIp="172.31.0.0/16",
            ),
            ec2.SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="21150",
                ToPort="21150",
                CidrIp="172.31.0.0/16",
            )
        ]

        # Add security group to template
        t.add_resource(secGrpCouchbase)

        return secGrpCouchbase

    keyname_param = t.add_parameter(Parameter(
        'KeyName', Type='String',
        Description='Name of an existing EC2 KeyPair to enable SSH access'
    ))

    secGrpCouchbase = createCouchbaseSecurityGroups(t)

    # Couchbase Server Instances
    for i in range(num_couchbase_servers):
        name = "{}{}".format(config.couchbase_server_prefix, i)
        instance = ec2.Instance(name)
        instance.ImageId = "ami-6d1c2007"  # centos7
        instance.InstanceType = couchbase_instance_type
        instance.SecurityGroups = [Ref(secGrpCouchbase)]
        instance.KeyName = Ref(keyname_param)
        instance.Tags = Tags(Name=name, Type="couchbaseserver")

        instance.BlockDeviceMappings = [
            ec2.BlockDeviceMapping(
                DeviceName="/dev/sda1",
                Ebs=ec2.EBSBlockDevice(
                    DeleteOnTermination=True,
                    VolumeSize=200,
                    VolumeType="gp2"
                )
            )
        ]
        t.add_resource(instance)

    # Sync Gw instances (ubuntu ami)
    for i in range(num_sync_gateway_servers):
        name = "{}{}".format(config.sync_gateway_prefix, i)
        instance = ec2.Instance(name)
        instance.ImageId = "ami-6d1c2007"  # centos7
        instance.InstanceType = sync_gateway_server_type
        instance.SecurityGroups = [Ref(secGrpCouchbase)]
        instance.KeyName = Ref(keyname_param)
        instance.BlockDeviceMappings = [
            ec2.BlockDeviceMapping(
                DeviceName="/dev/sda1",
                Ebs=ec2.EBSBlockDevice(
                    DeleteOnTermination=True,
                    VolumeSize=200,
                    VolumeType="gp2"
                )
            )
        ]

        # Make syncgateway0 a cache writer, and the rest cache readers
        # See https://github.com/couchbase/sync_gateway/wiki/Distributed-channel-cache-design-notes
        if i == 0:
            instance.Tags = Tags(Name=name, Type="syncgateway", CacheType="writer")
        else:
            instance.Tags = Tags(Name=name, Type="syncgateway")

        t.add_resource(instance)

    return t.to_json()
