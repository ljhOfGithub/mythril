"""This module contains representation classes for Solidity files, contracts
and source mappings."""
from typing import Dict, Set
import logging

import mythril.laser.ethereum.util as helper
from mythril.ethereum.evmcontract import EVMContract
from mythril.ethereum.util import get_solc_json
from mythril.exceptions import NoContractFoundError

log = logging.getLogger(__name__)


class SourceMapping:
    def __init__(self, solidity_file_idx, offset, length, lineno, mapping):
        """Representation of a source mapping for a Solidity file."""

        self.solidity_file_idx = solidity_file_idx
        self.offset = offset
        self.length = length
        self.lineno = lineno
        self.solc_mapping = mapping


class SolidityFile:
    """Representation of a file containing Solidity code."""

    def __init__(self, filename: str, data: str, full_contract_src_maps: Set[str]):#Set[str]：表示字符串的集合
        """
        Metadata class containing data regarding a specific solidity file
        :param filename: The filename of the solidity file
        :param data: The code of the solidity file
        :param full_contract_src_maps: The set of contract source mappings of all the contracts in the file
        """
        self.filename = filename
        self.data = data
        self.full_contract_src_maps = full_contract_src_maps
#元数据类，包含关于特定solidity文件的数据
#文件中所有合约的合约源映射集

class SourceCodeInfo:
    def __init__(self, filename, lineno, code, mapping):
        """Metadata class containing a code reference for a specific file."""

        self.filename = filename
        self.lineno = lineno
        self.code = code
        self.solc_mapping = mapping


def get_contracts_from_file(input_file, solc_settings_json=None, solc_binary="solc"):
    """

    :param input_file:
    :param solc_settings_json:
    :param solc_binary:
    """
    data = get_solc_json(
        input_file, solc_settings_json=solc_settings_json, solc_binary=solc_binary
    )
    #获取文件中的合约
    try:
        contract_names = data["contracts"][input_file].keys()#返回一个字典所有的键即合约名
    except KeyError:
        raise NoContractFoundError

    for contract_name in contract_names:
        if len(
            data["contracts"][input_file][contract_name]["evm"]["deployedBytecode"][
                "object"
            ]#["evm"]["deployedBytecode"] The list of function hashes
        ):
            yield SolidityContract(
                input_file=input_file,
                name=contract_name,
                solc_settings_json=solc_settings_json,
                solc_binary=solc_binary,
            )


class SolidityContract(EVMContract):
    """Representation of a Solidity contract."""
    #表示solidity合约
    def __init__(
        self, input_file, name=None, solc_settings_json=None, solc_binary="solc"
    ):
        data = get_solc_json(
            input_file, solc_settings_json=solc_settings_json, solc_binary=solc_binary
        )

        self.solc_indices = self.get_solc_indices(data)
        self.solc_json = data
        self.input_file = input_file
        has_contract = False

        # If a contract name has been specified, find the bytecode of that specific contract
        #如果指定了合同名称，查找该合同的字节码
        #获取json对象中的各个参数
        srcmap_constructor = []
        srcmap = []
        if name:
            contract = data["contracts"][input_file][name]
            if len(contract["evm"]["deployedBytecode"]["object"]):
                code = contract["evm"]["deployedBytecode"]["object"]
                creation_code = contract["evm"]["bytecode"]["object"]
                srcmap = contract["evm"]["deployedBytecode"]["sourceMap"].split(";")
                srcmap_constructor = contract["evm"]["bytecode"]["sourceMap"].split(";")
                has_contract = True

        # If no contract name is specified, get the last bytecode entry for the input file
        # 如果没有指定契约名称，则获取输入文件的最后一个字节码条目

        else:
            for contract_name, contract in sorted(
                data["contracts"][input_file].items()
            ):
                if len(contract["evm"]["deployedBytecode"]["object"]):
                    name = contract_name
                    code = contract["evm"]["deployedBytecode"]["object"]
                    creation_code = contract["evm"]["bytecode"]["object"]
                    srcmap = contract["evm"]["deployedBytecode"]["sourceMap"].split(";")
                    srcmap_constructor = contract["evm"]["bytecode"]["sourceMap"].split(
                        ";"
                    )
                    has_contract = True

        if not has_contract:
            raise NoContractFoundError

        self.mappings = []

        self.constructor_mappings = []

        self._get_solc_mappings(srcmap)
        self._get_solc_mappings(srcmap_constructor, constructor=True)

        super().__init__(code, creation_code, name=name)

    @staticmethod
    def get_sources(indices_data: Dict, source_data: Dict) -> None:
        """
        Get source indices mapping
        """
        #获取源索引映射
        if "generatedSources" not in source_data:
            return
        sources = source_data["generatedSources"]
        #对于某些实用程序例程，编译器生成“内部”源文件，这些文件不是原始输入的一部分，而是从源映射引用的。这些源文件及其标识符可以通过 output['contracts'][sourceName][contractName]['evm']['bytecode']['generatedSources'] .
        for source in sources:
            full_contract_src_maps = SolidityContract.get_full_contract_src_maps(
                source["ast"]
            )
            indices_data[source["id"]] = SolidityFile(
                source["name"], source["contents"], full_contract_src_maps
            )

    @staticmethod
    def get_solc_indices(data: Dict) -> Dict:
        """
        Returns solc file indices
        """
        indices: Dict = {}
        for contract_data in data["contracts"].values():#以列表返回字典中的所有值
            for source_data in contract_data.values():
                SolidityContract.get_sources(indices, source_data["evm"]["bytecode"])#十六进制字符串的字节码
                SolidityContract.get_sources(
                    indices, source_data["evm"]["deployedBytecode"]#函数哈希的列表
                )
        for source in data["sources"].values():
            full_contract_src_maps = SolidityContract.get_full_contract_src_maps(
                source["ast"]#获取某个合约的源映射
            )
            with open(source["ast"]["absolutePath"]) as f:
                code = f.read()
                indices[source["id"]] = SolidityFile(
                    source["ast"]["absolutePath"], code, full_contract_src_maps
                )
        return indices

    @staticmethod
    def get_full_contract_src_maps(ast: Dict) -> Set[str]:
        """
        Takes a solc AST and gets the src mappings for all the contracts defined in the top level of the ast
        :param ast: AST of the contract 合约的抽象语法树
        :return: The source maps
        """
        #添加ast中所有的需要记录的代码位置到集合中
        source_maps = set()
        if ast["nodeType"] == "SourceUnit":
            for child in ast["nodes"]:
                if child.get("contractKind"):
                    source_maps.add(child["src"])#src是代码位置，从具体的https://gist.github.com/afterburncallum/8eb6067794ba98513545080f61e7f1b6可以看出
        elif ast["nodeType"] == "YulBlock":
            for child in ast["statements"]:
                source_maps.add(child["src"])

        return source_maps

    def get_source_info(self, address, constructor=False):
        """

        :param address:
        :param constructor:
        :return:
        """
        disassembly = self.creation_disassembly if constructor else self.disassembly
        mappings = self.constructor_mappings if constructor else self.mappings
        index = helper.get_instruction_index(disassembly.instruction_list, address)
        file_index = mappings[index].solidity_file_idx

        if file_index == -1:
            # If issue is detected in an internal file如果在内部文件中检测到问题
            return None

        solidity_file = self.solc_indices[file_index]
        filename = solidity_file.filename

        offset = mappings[index].offset
        length = mappings[index].length

        code = solidity_file.data.encode("utf-8")[offset : offset + length].decode(
            "utf-8", errors="ignore"
        )
        lineno = mappings[index].lineno
        return SourceCodeInfo(filename, lineno, code, mappings[index].solc_mapping)

    def _is_autogenerated_code(self, offset: int, length: int, file_index: int) -> bool:
        """
        Checks whether the code is autogenerated or not
        :param offset: offset of the code
        :param length: length of the code
        :param file_index: file the code corresponds to
        :return: True if the code is internally generated, else false
        """

        if file_index == -1:
            return True
        # Handle the common code src map for the entire code.
        if (
            "{}:{}:{}".format(offset, length, file_index)
            in self.solc_indices[file_index].full_contract_src_maps
        ):
            return True

        return False

    def _get_solc_mappings(self, srcmap, constructor=False):
        """

        :param srcmap:
        :param constructor:
        """
        mappings = self.constructor_mappings if constructor else self.mappings
        prev_item = ""
        for item in srcmap:
            if item == "":
                item = prev_item
            mapping = item.split(":")

            if len(mapping) > 0 and len(mapping[0]) > 0:
                offset = int(mapping[0])

            if len(mapping) > 1 and len(mapping[1]) > 0:
                length = int(mapping[1])

            if len(mapping) > 2 and len(mapping[2]) > 0:
                idx = int(mapping[2])

            if self._is_autogenerated_code(offset, length, idx):
                lineno = None
            else:
                lineno = (
                    self.solc_indices[idx]
                    .data.encode("utf-8")[0:offset]
                    .count("\n".encode("utf-8"))
                    + 1
                )
            prev_item = item
            mappings.append(SourceMapping(idx, offset, length, lineno, item))
