#!/usr/bin/env python3

from pathlib import Path
from argparse import ArgumentParser
from tabulate import tabulate
from enum import Enum
from utils import ensure_min_python_version

import json
import sys

ensure_min_python_version()


class Action(Enum):
    VERIFY = 0
    SET = 1
    CLEAR = 2
    GET = 3

    def __str__(self):
        return self.name.lower()


class SettingKeyType(Enum):
    STRING_INPUT = 0
    YES_NO_INPUT = 1


class SettingKeyNames(Enum):
    CBS_VERSION = "cbs_version"
    SG_VERSION = "sg_version"
    AWS_REGION = "aws_region"
    CBS_SERVER_PREFIX = "cbs_server_prefix"
    SG_SERVER_PREFIX = "sg_server_prefix"
    CBS_ADMIN = "cbs_admin"

    def __str__(self):
        return self.value


class SettingKey:
    __data: dict
    __keyname: str
    __description: str
    __setting_type: SettingKeyType
    __fallback: object

    @staticmethod
    def all_keys():
        return [
            SettingKey(SettingKeyNames.CBS_VERSION, "Couchbase Server Version", SettingKeyType.STRING_INPUT, "6.5.0"),
            SettingKey(SettingKeyNames.SG_VERSION, "Sync Gateway Version", SettingKeyType.STRING_INPUT, "2.7.2"),
            SettingKey(SettingKeyNames.AWS_REGION, "Default region of AWS to use", SettingKeyType.STRING_INPUT,
                       "us-east-1"),
            SettingKey(SettingKeyNames.CBS_SERVER_PREFIX,
                       "The prefix to use when finding / creating with Couchbase Server instances",
                       SettingKeyType.STRING_INPUT, "couchbaseserver"),
            SettingKey(SettingKeyNames.CBS_ADMIN, "The administrator username for Couchbase Server instances",
                       SettingKeyType.STRING_INPUT, "Administrator"),
            SettingKey(SettingKeyNames.SG_SERVER_PREFIX,
                       "The prefix to use when finding / creating Sync Gateway instances",
                       SettingKeyType.STRING_INPUT, "syncgateway")
        ]

    @staticmethod
    def get_key(name: str):
        return next(key for key in SettingKey.all_keys() if key.name == name)

    def __init__(self, key_name: SettingKeyNames, description: str, setting_type: SettingKeyType, fallback: object):
        self.__keyname = str(key_name)
        self.__description = description
        self.__setting_type = setting_type
        self.__fallback = fallback

    @property
    def name(self):
        return self.__keyname

    @property
    def description(self):
        return self.__description

    @property
    def fallback(self):
        return self.__fallback

    @property
    def type(self):
        return self.__setting_type

    def __str__(self):
        return "{} ({})".format(self.__keyname, self.__description)


class Configuration:
    @staticmethod
    def _get_config_file():
        config_folder = Path.home() / "cluster_management"
        config_folder.mkdir(mode=0o755, exist_ok=True)
        return config_folder / "config.json"

    def load(self):
        config_file = Configuration._get_config_file()
        if not config_file.exists():
            return False

        with config_file.open(mode="r") as fin:
            self.__data = json.load(fin)

        return True

    def save(self):
        config_file = Configuration._get_config_file()
        with config_file.open(mode="w") as fout:
            json.dump(self.__data, fout)

    def get(self, key):
        val = self.__data.get(str(key))
        if val is None:
            setting_key = SettingKey.get_key(str(key))
            if setting_key is not None:
                return setting_key.fallback

        return val

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, val: object):
        if val is not None:
            self.__data[str(key)] = val
        else:
            self.__data.pop(str(key), None)

    def __str__(self):
        columns = ["Key", "Value (* = changed)", "Description"]
        values = []
        for key in SettingKey.all_keys():
            if key.name in self.__data:
                values.append([key.name, str(self.__data.get(key.name)) + " (*)", key.description])
            else:
                values.append([key.name, str(key.fallback), key.description])

        return tabulate(values, headers=columns)


def _prompt_config_val(msg: str, existing_val: object):
    next_input = ""
    first = True
    while True:
        if not first:
            print("Please enter a value...")
        if existing_val is not None:
            prompt_msg = "{} [{}]: ".format(msg, existing_val)
        else:
            prompt_msg = "{}: ".format(msg)

        next_input = input(prompt_msg)
        first = False
        if len(next_input.strip()) == 0 and existing_val is not None:
            return existing_val

        if len(next_input.strip()) > 0:
            return next_input


def _prompt_config_yn(msg: str, existing_val: bool):
    prompt_msg = "{} ((y)es|(n)o)".format(msg)
    while True:
        next_input = _prompt_config_val(prompt_msg, existing_val)
        if type(next_input) is bool:
            return next_input

        if len(next_input.strip()) == 0:
            continue

        if next_input[0].lower() == 'y':
            return True

        if next_input[0].lower() == 'n':
            return False

        print("Please enter a valid response...")


def _do_interactive_setup(config: Configuration):
    for key in SettingKey.all_keys():
        if key.type == SettingKeyType.STRING_INPUT:
            val = _prompt_config_val(key.description, config.get(key.name))
        else:
            val = _prompt_config_yn(key.description, config.get(key.name))

        if val != key.fallback:
            config[key.name] = val
        else:
            config[key.name] = None

    config.save()
    return 0


def _verify_config(config: Configuration):
    print()
    print(config)


if __name__ == "__main__":
    parser = ArgumentParser(prog="configure")
    subparsers = parser.add_subparsers(title="actions",
                                       description="Valid actions (omit for interactive)",
                                       help="Actions that this program is able to perform")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.set_defaults(action=Action.VERIFY)
    set_parser = subparsers.add_parser("set")
    set_parser.set_defaults(action=Action.SET)
    set_parser.add_argument("key", action="store", type=str,
                            help="The configuration key to set (use the verify command to see defined keys)")
    set_parser.add_argument("value", action="store", type=str,
                            help="The configuration value to set for the key")

    clear_parser = subparsers.add_parser("clear")
    clear_parser.set_defaults(action=Action.CLEAR)
    clear_parser.add_argument("key", action="store", type=str,
                              help="The configuration key to clear (use the verify command to see defined keys)")

    get_parser = subparsers.add_parser("get")
    get_parser.set_defaults(action=Action.GET)
    get_parser.add_argument("key", action="store", type=str,
                            help="The configuration key to get (use the verify command to see defined keys)")

    args = parser.parse_args()

    config = Configuration()
    config.load()
    if len(sys.argv) == 1:
        _do_interactive_setup(config)
        sys.exit(0)

    if args.action == Action.VERIFY:
        print()
        print(config)
    elif args.action == Action.SET:
        config[args.key] = args.value
        config.save()
    elif args.action == Action.CLEAR:
        config[args.key] = None
        config.save()
    elif args.action == Action.GET:
        val = config.get(args.key)
        if val is None:
            print("<not set>")
        else:
            print(val)
