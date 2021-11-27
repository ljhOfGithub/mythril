"""This module contains various utility functions regarding unit conversion and
solc integration."""
# 这个模块包含了各种关于单元转换和solc集成的实用函数
import binascii
import json
import sys
import os
import platform
import logging
import solc

from pathlib import Path
from subprocess import PIPE, Popen

from json.decoder import JSONDecodeError
from mythril.exceptions import CompilerError
from semantic_version import Version

if sys.version_info[1] >= 6:
    import solcx
    from solcx.exceptions import SolcNotInstalled

log = logging.getLogger(__name__)


def safe_decode(hex_encoded_string):
    """

    :param hex_encoded_string:
    :return:
    """
    if hex_encoded_string.startswith("0x"):
        return bytes.fromhex(hex_encoded_string[2:])
        #>>> bytes.fromhex('000102030405')
        #b'\x00\x01\x02\x03\x04\x05'
        #把十六进制转换为字节
    else:
        return bytes.fromhex(hex_encoded_string)


def get_solc_json(file, solc_binary="solc", solc_settings_json=None):
    """

    :param file:
    :param solc_binary:
    :param solc_settings_json:
    :return:
    """
    cmd = [solc_binary, "--standard-json", "--allow-paths", "."]#命令行的命令，使用子进程运行，默认编译器是官方的,--allow-paths允许用于import语句的路径
    settings = {}#如果 solc 用选项调用 --standard-json ，它将期望在标准输入上有一个JSON输入（如下所述），并在标准输出上返回一个JSON输出。
    if solc_settings_json:#编译的默认设置
        with open(solc_settings_json) as f:
            settings = json.load(f)
    settings.update(
        {
            "optimizer": {"enabled": False},
            "outputSelection": {
                "*": {
                    "": ["ast"],
                    "*": [
                        "metadata",
                        "evm.bytecode",
                        "evm.deployedBytecode",
                        "evm.methodIdentifiers",
                    ],
                }
            },
        }
    )

    input_json = json.dumps(
        {
            "language": "Solidity",
            "sources": {file: {"urls": [file]}},
            "settings": settings,
        }
    )#用于将 Python 对象编码成 JSON 字符串

    try:
        p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)#开子进程编译solidity文件为json
        stdout, stderr = p.communicate(bytes(input_json, "utf8"))
#Popen.communicate(input=None)：与子进程进行交互。向stdin发送数据，或从stdout和stderr中读取数据。可选参数input指定发送到子进程的参数。
#Communicate()返回一个元组：(stdoutdata, stderrdata)。注意：如果希望通过进程的stdin向其发送数据，在创建Popen对象的时候，参数stdin必须被设置为PIPE。同样，如果希望从stdout和stderr获取数据，必须将stdout和stderr设置为PIPE
    except FileNotFoundError:
        raise CompilerError(
            "Compiler not found. Make sure that solc is installed and in PATH, or set the SOLC environment variable."
        )

    out = stdout.decode("UTF-8")#bytes解码

    try:
        result = json.loads(out)#用于解码 JSON 数据。该函数返回 Python 字段的数据类型
    except JSONDecodeError as e:
        log.error(f"Encountered a decode error, stdout:{out}, stderr: {stderr}")
        raise e

    for error in result.get("errors", []):
        if error["severity"] == "error":
            raise CompilerError(
                "Solc experienced a fatal error.\n\n%s" % error["formattedMessage"]
            )

    return result


def get_random_address():
    """

    :return:
    """
    return binascii.b2a_hex(os.urandom(20)).decode("UTF-8")

#binascii.b2a_hex(data[, sep[, bytes_per_sep=1]])
#binascii.hexlify(data[, sep[, bytes_per_sep=1]])
#返回二进制数据 data 的十六进制表示形式。 data 的每个字节都被转换为相应的2位十六进制表示形式。因此返回的字节对象的长度是 data 的两倍。
#os.urandom函数用来获取一个指定长度的随机bytes对象，python的这个函数实际上是在读取OS操作系统提供的随机源
def get_indexed_address(index):
    """

    :param index:
    :return:
    """
    return "0x" + (hex(index)[2:] * 40)


def solc_exists(version):
    """

    :param version:
    :return:
    """

    default_binary = "/usr/bin/solc"#返回solc所在路径
    if sys.version_info[1] >= 6:#判断python版本是否大于等于3.6
        if platform.system() == "Darwin":
            solcx.import_installed_solc()
        solcx.install_solc("v" + version)
        solcx.set_solc_version("v" + version)
        solc_binary = solcx.install.get_executable()
        return solc_binary
    elif Version("0.4.2") <= Version(version) <= Version("0.4.25"):
        if not solc.main.is_solc_available():
            solc.install_solc("v" + version)
            solc_binary = solc.install.get_executable_path("v" + version)
            return solc_binary
        else:
            solc_binaries = [
                os.path.join(
                    os.environ.get("HOME", str(Path.home())),
                    ".py-solc/solc-v" + version,
                    "bin/solc",
                )  # py-solc setup
            ]
            for solc_path in solc_binaries:
                if os.path.exists(solc_path):
                    return solc_path
    elif os.path.exists(default_binary):
        return default_binary

    else:
        return None
