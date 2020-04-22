#!/usr/bin/env python3

from pathlib import Path
from argparse import ArgumentParser
from tabulate import tabulate
from enum import Enum
from utils import ensure_min_python_version

import json
import sys

ensure_min_python_version()


class NotConfiguredException(Exception):
    def __init__(self):
        super().__init__("No configuration detected, please run configure.py")


class InvalidConfigurationException(Exception):
    pass


class SettingKeyType(Enum):
    STRING_INPUT = 0
    YES_NO_INPUT = 1


class SettingKeyNames(Enum):
    CBS_VERSION = "cbs_version"
    SG_VERSION = "sg_version"

    def __str__(self):
        return self.value


class SettingKey:
    __data: dict

    @staticmethod
    def all_keys():
        return [
            SettingKey(SettingKeyNames.CBS_VERSION, "Couchbase Server Version", SettingKeyType.STRING_INPUT),
            SettingKey(SettingKeyNames.SG_VERSION, "Sync Gateway Version", SettingKeyType.STRING_INPUT)
        ]

    def __init__(self, key_name: SettingKeyNames, description: str, setting_type: SettingKeyType):
        self.__keyname = str(key_name)
        self.__description = description
        self.__setting_type = setting_type

    @property
    def name(self):
        return self.__keyname

    @property
    def description(self):
        return self.__description

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
        return self.__data.get(str(key))

    def verify(self):
        return SettingKeyNames.CBS_VERSION in self.__data and SettingKeyNames.SG_VERSION in self.__data

    def __getitem__(self, key):
        return self.__data[str(key)]

    def __setitem__(self, key, val: object):
        self.__data[str(key)] = val

    def __str__(self):
        columns = ["Setting", "Value"]
        values = []
        for key in SettingKey.all_keys():
            if key.name in self.__data:
                values.append([key.description, self.__data.get(key.name)])

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


if __name__ == "__main__":
    parser = ArgumentParser(prog="create_cluster")
    parser.add_argument("--verify",
                        action="store_true", dest="verify",
                        help="Just print out the existing values")

    args = parser.parse_args()
    config = Configuration()
    config.load()
    if args.verify:
        print()
        print(config)
        sys.exit(0)

    for key in SettingKey.all_keys():
        if key.type == SettingKeyType.STRING_INPUT:
            config[key.name] = _prompt_config_val(key.description, config.get(key.name))
        else:
            config[key.name] = _prompt_config_yn(key.description, config.get(key.name))

    config.verify()
    config.save()
