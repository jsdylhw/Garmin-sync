from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)

BASE_TYPE_SIZES = {
    0: 1,
    1: 1,
    2: 1,
    7: 1,
    10: 1,
    13: 1,
    131: 2,
    132: 2,
    133: 4,
    134: 4,
    136: 4,
    137: 8,
    139: 2,
    140: 4,
}

INVALID_VALUES = {
    0: 0xFF,
    1: 0x7F,
    2: 0xFF,
    7: None,
    10: 0x00,
    13: None,
    131: 0x7FFF,
    132: 0xFFFF,
    133: 0x7FFFFFFF,
    134: 0xFFFFFFFF,
    136: struct.unpack("<I", struct.pack("<f", 0xFFFFFFFF))[0],
    137: struct.unpack("<Q", struct.pack("<d", float("nan")))[0],
    139: 0x0000,
    140: 0x00000000,
}


@dataclass
class FieldDefinition:
    number: int
    size: int
    base_type: int
    offset: int


@dataclass
class MessageDefinition:
    local_number: int
    global_number: int
    endian: str
    fields: list[FieldDefinition]


@dataclass
class FitMessage:
    global_number: int
    local_number: int
    fields_by_number: dict[int, Any]
    developer_fields: dict[int, Any]


def crc16(data: bytes | bytearray) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
            crc &= 0xFFFF
    return crc


class FitReader:
    def read_file(self, path: str | Path) -> list[FitMessage]:
        buffer = Path(path).read_bytes()
        self._validate_file(buffer)
        return self._parse_messages(buffer)

    def _validate_file(self, buffer: bytes) -> None:
        if buffer[8:12] != b".FIT":
            raise ValueError("输入文件不是合法的 FIT 文件")
        header_size = buffer[0]
        stored_header_crc = struct.unpack_from("<H", buffer, header_size - 2)[0]
        calculated_header_crc = crc16(buffer[: header_size - 2])
        if stored_header_crc != calculated_header_crc:
            raise ValueError("FIT 文件头 CRC 校验失败")
        stored_file_crc = struct.unpack_from("<H", buffer, len(buffer) - 2)[0]
        calculated_file_crc = crc16(buffer[:-2])
        if stored_file_crc != calculated_file_crc:
            raise ValueError("FIT 文件 CRC 校验失败")

    def _parse_messages(self, buffer: bytes) -> list[FitMessage]:
        header_size = buffer[0]
        data_size = struct.unpack_from("<I", buffer, 4)[0]
        data_end = header_size + data_size
        position = header_size
        definitions: dict[int, MessageDefinition] = {}
        previous_timestamps: dict[int, int] = {}
        messages: list[FitMessage] = []

        while position < data_end:
            header = buffer[position]
            position += 1

            if header & 0x80:
                local_number = (header >> 5) & 0x03
                definition = definitions[local_number]
                previous_timestamp = previous_timestamps.get(local_number)
                if previous_timestamp is None:
                    raise ValueError("遇到压缩时间戳消息时缺少前序时间戳")
                current_timestamp = self._resolve_compressed_timestamp(previous_timestamp, header)
                previous_timestamps[local_number] = current_timestamp
                field_values, position = self._read_data_fields(buffer, position, definition)
                field_values[253] = self._fit_datetime(current_timestamp)
                messages.append(
                    FitMessage(
                        global_number=definition.global_number,
                        local_number=local_number,
                        fields_by_number=field_values,
                        developer_fields={},
                    )
                )
                continue

            if header & 0x40:
                definition, position = self._parse_definition(buffer, position, header)
                definitions[definition.local_number] = definition
                continue

            local_number = header & 0x0F
            definition = definitions[local_number]
            field_values, position = self._read_data_fields(buffer, position, definition)
            timestamp = field_values.get(253)
            if isinstance(timestamp, datetime):
                previous_timestamps[local_number] = self._datetime_to_fit(timestamp)
            messages.append(
                FitMessage(
                    global_number=definition.global_number,
                    local_number=local_number,
                    fields_by_number=field_values,
                    developer_fields={},
                )
            )

        return messages

    def _parse_definition(self, buffer: bytes, position: int, header: int) -> tuple[MessageDefinition, int]:
        local_number = header & 0x0F
        architecture = buffer[position + 1]
        endian = ">" if architecture else "<"
        global_number = struct.unpack_from(f"{endian}H", buffer, position + 2)[0]
        field_count = buffer[position + 4]
        cursor = position + 5
        fields: list[FieldDefinition] = []
        field_offset = 0
        for _ in range(field_count):
            fields.append(
                FieldDefinition(
                    number=buffer[cursor],
                    size=buffer[cursor + 1],
                    base_type=buffer[cursor + 2],
                    offset=field_offset,
                )
            )
            field_offset += buffer[cursor + 1]
            cursor += 3
        if header & 0x20:
            developer_field_count = buffer[cursor]
            cursor += 1 + developer_field_count * 3
        return MessageDefinition(local_number, global_number, endian, fields), cursor

    def _read_data_fields(
        self,
        buffer: bytes,
        position: int,
        definition: MessageDefinition,
    ) -> tuple[dict[int, Any], int]:
        values: dict[int, Any] = {}
        for field in definition.fields:
            raw = buffer[position : position + field.size]
            values[field.number] = self._decode_field(raw, field, definition.endian)
            position += field.size
        return values, position

    def _decode_field(self, raw: bytes, field: FieldDefinition, endian: str) -> Any:
        base_type = field.base_type & 0x1F | (field.base_type & 0x80)
        if base_type == 7:
            text = raw.split(b"\x00", 1)[0].decode("utf-8", errors="ignore").strip()
            return text or None
        if base_type == 13:
            return raw

        unit_size = BASE_TYPE_SIZES.get(base_type)
        if unit_size is None:
            return raw
        if unit_size == field.size:
            return self._decode_scalar(raw, base_type, endian)
        if field.size % unit_size != 0:
            return raw
        values = []
        for offset in range(0, field.size, unit_size):
            decoded = self._decode_scalar(raw[offset : offset + unit_size], base_type, endian)
            if decoded is not None:
                values.append(decoded)
        return values

    def _decode_scalar(self, raw: bytes, base_type: int, endian: str) -> Any:
        if base_type == 0:
            value = raw[0]
        elif base_type == 1:
            value = struct.unpack("b", raw)[0]
        elif base_type in {2, 10}:
            value = raw[0]
        elif base_type == 131:
            value = struct.unpack(f"{endian}h", raw)[0]
        elif base_type in {132, 139}:
            value = struct.unpack(f"{endian}H", raw)[0]
        elif base_type == 133:
            value = struct.unpack(f"{endian}i", raw)[0]
        elif base_type in {134, 140}:
            value = struct.unpack(f"{endian}I", raw)[0]
        elif base_type == 136:
            value = struct.unpack(f"{endian}f", raw)[0]
        elif base_type == 137:
            value = struct.unpack(f"{endian}d", raw)[0]
        else:
            return raw

        invalid_value = INVALID_VALUES.get(base_type)
        if invalid_value is not None and value == invalid_value:
            return None
        return value

    def _resolve_compressed_timestamp(self, previous_timestamp: int, header: int) -> int:
        candidate = (previous_timestamp & 0xFFFFFFE0) + (header & 0x1F)
        if candidate < previous_timestamp:
            candidate += 0x20
        return candidate

    def _fit_datetime(self, seconds_since_fit_epoch: int) -> datetime:
        return FIT_EPOCH + timedelta(seconds=seconds_since_fit_epoch)

    def _datetime_to_fit(self, value: datetime) -> int:
        return int((value.astimezone(timezone.utc) - FIT_EPOCH).total_seconds())
