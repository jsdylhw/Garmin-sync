from __future__ import annotations

import struct
from pathlib import Path

from fit_clone_current_date import crc16
from fit_activity_transformer.writer.activity_builder import BuiltActivity
from fit_activity_transformer.writer.fit_message_builder import FitMessageBuilder


class FitWriter:
    """负责生成完整 FIT 文件头、数据区和 CRC 并写入磁盘。"""

    def __init__(self, protocol_version: int = 16, profile_version: int = 21192) -> None:
        """初始化 FIT 写出器。

        参数:
            protocol_version: FIT 协议版本号。
            profile_version: FIT profile 版本号。
        """

        self.protocol_version = protocol_version
        self.profile_version = profile_version
        self.message_builder = FitMessageBuilder()

    def write(self, activity: BuiltActivity, output_path: str | Path) -> Path:
        """将活动对象写出为 FIT 文件。

        参数:
            activity: 待写出的活动对象。
            output_path: 输出 FIT 文件路径。

        返回:
            实际写出的文件路径。
        """

        output = Path(output_path)
        data = self.message_builder.build_messages(activity)
        header = self._build_header(len(data))
        file_crc = struct.pack("<H", crc16(header + data))
        output.write_bytes(header + data + file_crc)
        return output

    def _build_header(self, data_size: int) -> bytes:
        """构造 FIT 文件头并附带头部 CRC。

        参数:
            data_size: 数据区字节长度。

        返回:
            完整的 FIT 文件头字节。
        """

        header_without_crc = bytearray()
        header_without_crc.append(14)
        header_without_crc.append(self.protocol_version)
        header_without_crc.extend(struct.pack("<H", self.profile_version))
        header_without_crc.extend(struct.pack("<I", data_size))
        header_without_crc.extend(b".FIT")
        header_crc = struct.pack("<H", crc16(header_without_crc))
        return bytes(header_without_crc + header_crc)
