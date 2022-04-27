#!/usr/bin/env python3

from getpass import getpass
from enum import Enum
from tabulate import tabulate

import os

try:
    import keyring
    HAVE_KEYRING = True
except ImportError:
    HAVE_KEYRING = False


class CredentialName(Enum):
    CM_CBS_PASS = "The administrator password for Couchbase Server instances"
    CM_SSHKEY_PASS = "The password for the SSH key used to connect to EC2"

    def __str__(self):
        return self.name


class Credential:
    __value: str

    def __init__(self, description: str, value: str = None, service_name: str = None, username: str = None):
        if value is not None:
            self.__value = value
            return

        if service_name is not None:
            found_value = os.environ.get(service_name)
            if found_value is not None:
                self.__value = found_value
                return

            if HAVE_KEYRING:
                found_value = keyring.get_password(service_name, username)
                if found_value is not None:
                    self.__value = found_value
                    return

        self.__value = getpass("No value found for {}, please enter: ".format(description))

    def __str__(self):
        return self.__value


if __name__ == "__main__":
    print()
    print("When this script is run, it displays the credential help.  Each credential used by")
    print("the framework, if not provided on the command line, is resolved using a number of methods.")
    print("First, an environment variable is consulted (see the list below).  If it is not found there")
    print("then the optional step is taken of checking the keyring service (if the python module")
    print("'keyring' is installed it will check using the service that corresponds with the keyname")
    print("argument that the same command takes and a username identical to the environment variable.")
    print("If it still is not found, a password prompt is displayed to get the value")
    print()

    variables = list([str(x), x.value] for x in CredentialName)
    print(tabulate(variables, ["Variable Name", "Description"]))
