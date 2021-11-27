"""This module contains the class used to represent disassembly code."""
from mythril.ethereum import util
from mythril.disassembler import asm
from mythril.support.signatures import SignatureDB

from typing import Dict, List, Tuple


class Disassembly(object):
    """Disassembly class.

    Stores bytecode, and its disassembly.
    Additionally it will gather the following information on the existing functions in the disassembled code:
    - function hashes
    - function name to entry point mapping
    - function entry point to function name mapping
    """
#存储字节码及其反汇编
#此外，它将收集以下关于反汇编代码中现有函数的信息:
#函数入口点到函数名的映射
    def __init__(self, code: str, enable_online_lookup: bool = False) -> None:
        """

        :param code:
        :param enable_online_lookup:
        """
        self.bytecode = code
        self.instruction_list = asm.disassemble(util.safe_decode(code))

        self.func_hashes = []  # type: List[str]
        self.function_name_to_address = {}  # type: Dict[str, int] 函数名到地址的字典映射
        self.address_to_function_name = {}  # type: Dict[int, str] 地址到函数名的字典映射
        self.enable_online_lookup = enable_online_lookup
        self.assign_bytecode(bytecode=code)

    def assign_bytecode(self, bytecode):
        self.bytecode = bytecode
        # open from default locations
        # control if you want to have online signature hash lookups控制是否要进行在线签名散列查找
        signatures = SignatureDB(enable_online_lookup=self.enable_online_lookup)
        self.instruction_list = asm.disassemble(util.safe_decode(bytecode))
        # Need to take from PUSH1 to PUSH4 because solc seems to remove excess 0s at the beginning for optimizing
        #需要从PUSH1到PUSH4，因为solc似乎删除多余的0在优化的开始
        jump_table_indices = asm.find_op_code_sequence(
            [("PUSH1", "PUSH2", "PUSH3", "PUSH4"), ("EQ",)], self.instruction_list
        )

        for index in jump_table_indices:
            function_hash, jump_target, function_name = get_function_info(
                index, self.instruction_list, signatures
            )
            self.func_hashes.append(function_hash)
            if jump_target is not None and function_name is not None:
                self.function_name_to_address[function_name] = jump_target
                self.address_to_function_name[jump_target] = function_name

    def get_easm(self):
        """

        :return:
        """
        return asm.instruction_list_to_easm(self.instruction_list)


def get_function_info(
    index: int, instruction_list: list, signature_database: SignatureDB
) -> Tuple[str, int, str]:
    """Finds the function information for a call table entry Solidity uses the
    first 4 bytes of the calldata to indicate which function the message call
    should execute The generated code that directs execution to the correct
    function looks like this:

    - PUSH function_hash
    - EQ
    - PUSH entry_point
    - JUMPI

    This function takes an index that points to the first instruction, and from that finds out the function hash,
    function entry and the function name.

    :param index: Start of the entry pattern
    :param instruction_list: Instruction list for the contract that is being analyzed
    :param signature_database: Database used to map function hashes to their respective function names
    :return: function hash, function entry point, function name
    """
    #生成的代码将执行指向正确的函数，如下所示
    #这个函数接受指向第一个指令的索引，并从中找出函数哈希值、函数入口和函数名。
    #函数入口代码负责分配函数所需的任何堆栈空间
    # Append with missing 0s at the beginning
    function_hash = "0x" + instruction_list[index]["argument"][2:].rjust(8, "0")
    function_names = signature_database.get(function_hash)

    if len(function_names) > 0:
        function_name = function_names[0]
    else:
        function_name = "_function_" + function_hash

    try:
        offset = instruction_list[index + 2]["argument"]
        entry_point = int(offset, 16)
    except (KeyError, IndexError):
        return function_hash, None, None

    return function_hash, entry_point, function_name
