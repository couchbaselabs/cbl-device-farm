# CBL Server Orchestration for Device Farm

This repo contains a python implementation of a program that can use EC2 to set up an arbitrary number of Couchbase Servers and Sync Gateways for use with testing against a device farm containing a Couchbase Lite based application.

## Prerequisites

This implementation uses the Couchbase Python SDK, and so the [requirements](https://docs.couchbase.com/python-sdk/current/start-using-sdk.html#requirements) for that SDK must be satisfied first.  After that, the required python modules must be installed by using `pip install -r requirements.txt`.  Lastly, you must be configured to use AWS services from the command line.  The easiest way to do that is to install the [AWS Command Line Tools](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) and run `aws configure`

Also, you must run `git submodule update --init` after cloning to pick up the couchbase-cli.

## Examples

## Create an EC2 Stack
---

```
usage: create_cluster [-h] [--num-servers NUM_SERVERS]
                      [--server-type SERVER_TYPE]
                      [--num-sync-gateways NUM_SYNC_GATEWAYS]
                      [--sync-gateway-type SYNC_GATEWAY_TYPE]
                      [--region REGION]
                      stackname keyname

positional arguments:
  stackname             name for your cluster
  keyname               The EC2 keyname to install on all the instances

optional arguments:
  -h, --help            show this help message and exit
  --num-servers NUM_SERVERS
                        number of couchbase server instances
  --server-type SERVER_TYPE
                        EC2 instance type for couchbase server (default:
                        m3.medium)
  --num-sync-gateways NUM_SYNC_GATEWAYS
                        number of sync_gateway instances
  --sync-gateway-type SYNC_GATEWAY_TYPE
                        EC2 instance type for sync_gateway type (default:
                        m3.medium)
  --region REGION       The AWS region to use (default: us-east-1)
```

Create an EC2 stack named "device-farm" using the keyname "jborden" for SSH access with 3 m3.large instances configured for Couchbase Server, and 1 m3.medium (default) instance configured for Sync Gateway

`./create_cluster.py device-farm jborden --num-servers=3 --server-type=m3.large --num-sync-gateways=1`

## Install Couchbase Server
---

```
usage: install_couchbase_server [-h] [--region REGION]
                                [--server-name-prefix SERVERNAME]
                                [--ssh-key SSHKEY] [--setup-only]
                                keyname

positional arguments:
  keyname               The name of the SSH key that the EC2 instances are
                        using

optional arguments:
  -h, --help            show this help message and exit
  --region REGION       The EC2 region to query (default us-east-1)
  --server-name-prefix SERVERNAME
                        The name of the server to use to reset the Couchbase
                        cluster (default couchbaseserver)
  --ssh-key SSHKEY      The key to connect to EC2 instances
  --setup-only          Skip the program installation, and configure only
  ```

Install Couchbase Server to all the instances in EC2 that are setup with the "jborden" key and whose name starts with couchbaseserver (default), using the provided private key to connect.  If `--setup-only` is passed then installation is skipped and the cluster is checked to make sure that all nodes are reported correctly (i.e. The number of nodes reported by Couchbase Server is the same as the number of found instances) and fixed if needed.

`./install_couchbase_server.py jborden --ssh-key ~/.ssh/aws_jborden.pem`

## Install Sync Gateway
---

```
usage: install_sync_gateway [-h] [--region REGION]
                            [--server-name-prefix SERVERNAME]
                            [--sg-name-prefix SGNAME] [--ssh-key SSHKEY]
                            [--setup-only]
                            keyname

positional arguments:
  keyname               The name of the SSH key that the EC2 instances are
                        using

optional arguments:
  -h, --help            show this help message and exit
  --region REGION       The EC2 region to query (default us-east-1)
  --server-name-prefix SERVERNAME
                        The prefix of the server(s) to use for Couchbase
                        Server (default couchbaseserver)
  --sg-name-prefix SGNAME
                        The prefix of the server(s) to use for Sync Gateway
                        (default syncgateway)
  --ssh-key SSHKEY      The key to connect to EC2 instances
  --setup-only          Skip the program installation, and configure only
  ```

  Install Sync Gateway to all instances in EC2 that have the keyname "jborden" and whose name starts with "syncgateway" (default), using the provided private key to connect.  A config will be deployed so that Sync Gateway uses the first instance found with the prefix "couchbaseserver" (default).  If `--setup-only` is passed then only the second step is performed.

  `./install_sync_gateway.py jborden --ssh-key ~/.ssh/aws_jborden.pem`

  ## Reset Cluster State
  ---

  ```
  usage: reset_cluster [-h] [--region REGION] [--server-name-prefix SERVERNAME]
                     [--bucket-name BUCKETNAME] [--sg-name-prefix SGNAME]
                     [--ssh-key SSHKEY]
                     keyname cbuser cbpass

positional arguments:
  keyname               The name of the SSH key that the EC2 instances are
                        using
  cbuser                The user to authenticate with when resetting the
                        server
  cbpass                The password to authenticate with when resetting the
                        server

optional arguments:
  -h, --help            show this help message and exit
  --region REGION       The EC2 region to query (default us-east-1)
  --server-name-prefix SERVERNAME
                        The prefix of the Couchbase Server nodes in EC2
                        (default couchbaseserver)
  --bucket-name BUCKETNAME
                        The name of the bucket to reset (default device-farm-
                        data)
  --sg-name-prefix SGNAME
                        The prefix of the Sync Gateway instance names in EC2
                        (default syncgateway)
  --ssh-key SSHKEY      The key to connect to EC2 instances
  ```

  The following command will perform these steps:
  
  1. Connect to all EC2 instances whose name starts with "syncgateway" (default) and that use the "jborden" EC2 key pair using the provided private key and stop the Sync Gateway service
  1. Connect to the first EC2 instance whose name starts with "couchbaseserver" (default) and that uses the "jborden" EC2 key pair using the provided private key and reset all the external hostnames for the nodes in the cluster (they may have changed due to starting and stopping EC2 instances).
  1. Flush the device-farm-data bucket (default) using the provided Couchbase Server RBAC username and password (bucket_manager / bucket)
  1. Connect to the previous sync gateway nodes again and copy a new config file pointing to the reset Couchbase cluster, and start the Sync Gateway service using the new config

  `./reset_cluster.py jborden bucket_manager bucket --ssh-key=$HOME/.ssh/aws_jborden.pem`

## Start Up / Shut Down EC2 Cluster
---

```
usage: change_cluster_state.py [-h] [--region REGION]
                               keyname {STOPPED,RUNNING}

positional arguments:
  keyname            The name of the SSH key that the EC2 instances are using
  {STOPPED,RUNNING}  The state to set the cluster into

optional arguments:
  -h, --help         show this help message and exit
  --region REGION    The EC2 region (default us-east-1)
  ```

  The following command will shut down all instances in the cluster using the EC2 key pair "jborden" (to start up, use `RUNNING` instead of `STOPPED`)

  `./change_cluster_state.py jborden STOPPED`

  ## Find Instance
  ---

  ```
  usage: query_cluster [-h] [--region REGION] keyname {STOPPED,RUNNING}

positional arguments:
  keyname            The name of the SSH key that the EC2 instances are using
  {STOPPED,RUNNING}  The state of the instances to be found

optional arguments:
  -h, --help         show this help message and exit
  --region REGION    The EC2 region to query (default us-east-1)
  ```

  The following command will return information about instances in the `RUNNING` state that use the "jborden" EC2 key pair.

  `./query_cluster.py jborden RUNNING`