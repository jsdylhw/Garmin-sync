from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path


FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)
PREFERRED_ANCHORS = (
    (18, 2),
    (19, 2),
    (20, 253),
    (34, 253),
    (0, 4),
)
PATCHABLE_FIELDS = {
    0: {4},
    18: {2, 253},
    19: {2, 253},
    20: {253},
    21: {253},
    22: {253},
    23: {253},
    34: {5, 253},
    79: {253},
    104: {253},
    113: {253},
    141: {253},
    162: {253},
    216: {253},
    288: {253},
    312: {253},
    313: {253},
    325: {253},
    326: {253},
    327: {253},
    394: {253},
    534: {253},
}
INVALID_VALUES = {
    1: {0xFF},
    2: {0xFFFF},
    4: {0xFFFFFFFF},
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


def normalize_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.exists():
        return path
    candidate = Path(raw_path.replace("\\", "/"))
    return candidate


def fit_to_datetime(value: int) -> datetime:
    return FIT_EPOCH + timedelta(seconds=value)


def datetime_to_fit(value: datetime) -> int:
    return int((value.astimezone(timezone.utc) - FIT_EPOCH).total_seconds())


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


def read_unsigned(buffer: bytes | bytearray, start: int, size: int, endian: str) -> int:
    if size == 1:
        return buffer[start]
    if size == 2:
        return struct.unpack_from(f"{endian}H", buffer, start)[0]
    if size == 4:
        return struct.unpack_from(f"{endian}I", buffer, start)[0]
    raise ValueError(f"不支持读取 {size} 字节字段")


def write_unsigned(buffer: bytearray, start: int, size: int, endian: str, value: int) -> None:
    if size == 1:
        buffer[start] = value
        return
    if size == 2:
        struct.pack_into(f"{endian}H", buffer, start, value)
        return
    if size == 4:
        struct.pack_into(f"{endian}I", buffer, start, value)
        return
    raise ValueError(f"不支持写入 {size} 字节字段")


def parse_definition(buffer: bytes | bytearray, position: int, header: int) -> tuple[MessageDefinition, int]:
    local_number = header & 0x0F
    architecture = buffer[position + 1]
    endian = ">" if architecture else "<"
    global_number = struct.unpack_from(f"{endian}H", buffer, position + 2)[0]
    field_count = buffer[position + 4]
    cursor = position + 5
    fields: list[FieldDefinition] = []
    field_offset = 0
    for _ in range(field_count):
        field_number = buffer[cursor]
        field_size = buffer[cursor + 1]
        base_type = buffer[cursor + 2]
        fields.append(FieldDefinition(field_number, field_size, base_type, field_offset))
        cursor += 3
        field_offset += field_size
    if header & 0x20:
        developer_field_count = buffer[cursor]
        cursor += 1 + developer_field_count * 3
    return MessageDefinition(local_number, global_number, endian, fields), cursor


def resolve_compressed_timestamp(previous_timestamp: int, header: int) -> int:
    candidate = (previous_timestamp & 0xFFFFFFE0) + (header & 0x1F)
    if candidate < previous_timestamp:
        candidate += 0x20
    return candidate


def extract_anchor_timestamp(buffer: bytes | bytearray) -> int:
    header_size = buffer[0]
    data_size = struct.unpack_from("<I", buffer, 4)[0]
    data_end = header_size + data_size
    position = header_size
    definitions: dict[int, MessageDefinition] = {}
    previous_timestamps: dict[int, int] = {}
    discovered: dict[tuple[int, int], int] = {}

    while position < data_end:
        header_position = position
        header = buffer[position]
        position += 1

        if header & 0x80:
            local_number = (header >> 5) & 0x03
            definition = definitions[local_number]
            previous_timestamp = previous_timestamps.get(local_number)
            if previous_timestamp is None:
                raise ValueError("遇到压缩时间戳消息时缺少前序时间戳")
            current_timestamp = resolve_compressed_timestamp(previous_timestamp, header)
            previous_timestamps[local_number] = current_timestamp
            if (definition.global_number, 253) not in discovered:
                discovered[(definition.global_number, 253)] = current_timestamp
            position += sum(field.size for field in definition.fields)
            continue

        if header & 0x40:
            definition, position = parse_definition(buffer, position, header)
            definitions[definition.local_number] = definition
            continue

        local_number = header & 0x0F
        definition = definitions[local_number]
        data_start = position
        for field in definition.fields:
            field_start = data_start + field.offset
            field_value = read_unsigned(buffer, field_start, field.size, definition.endian) if field.size in {1, 2, 4} else None
            if field.number == 253 and field_value is not None and field.size == 4 and field_value not in INVALID_VALUES[4]:
                previous_timestamps[local_number] = field_value
            if (
                field.number is not None
                and field_value is not None
                and (definition.global_number, field.number) not in discovered
                and field.size in {1, 2, 4}
                and field_value not in INVALID_VALUES[field.size]
            ):
                discovered[(definition.global_number, field.number)] = field_value
        position += sum(field.size for field in definition.fields)

    for anchor in PREFERRED_ANCHORS:
        if anchor in discovered:
            return discovered[anchor]
    raise ValueError("未找到可用于复制日期的时间锚点")


def build_target_timestamp(source_timestamp: int, mode: str, target_datetime_text: str | None = None) -> int:
    source_datetime = fit_to_datetime(source_timestamp)
    local_timezone = datetime.now().astimezone().tzinfo or timezone.utc
    source_local = source_datetime.astimezone(local_timezone)
    now_local = datetime.now(local_timezone)

    if target_datetime_text:
        target_local = datetime.strptime(target_datetime_text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=local_timezone)
        return datetime_to_fit(target_local.astimezone(timezone.utc))

    if mode == "today":
        target_local = datetime.combine(now_local.date(), time(source_local.hour, source_local.minute, source_local.second), local_timezone)
    else:
        target_local = now_local

    return datetime_to_fit(target_local.astimezone(timezone.utc))


def should_patch_field(global_number: int, field: FieldDefinition) -> bool:
    return field.size == 4 and field.number in PATCHABLE_FIELDS.get(global_number, set())


def clone_fit_with_shift(
    source_path: Path,
    output_path: Path,
    mode: str,
    target_datetime_text: str | None = None,
) -> tuple[datetime, datetime]:
    buffer = bytearray(source_path.read_bytes())
    if buffer[8:12] != b".FIT":
        raise ValueError("输入文件不是合法的 FIT 文件")

    header_size = buffer[0]
    data_size = struct.unpack_from("<I", buffer, 4)[0]
    data_end = header_size + data_size

    stored_header_crc = struct.unpack_from("<H", buffer, header_size - 2)[0]
    calculated_header_crc = crc16(buffer[: header_size - 2])
    if stored_header_crc != calculated_header_crc:
        raise ValueError("FIT 文件头 CRC 校验失败")

    stored_file_crc = struct.unpack_from("<H", buffer, len(buffer) - 2)[0]
    calculated_file_crc = crc16(buffer[:-2])
    if stored_file_crc != calculated_file_crc:
        raise ValueError("FIT 文件 CRC 校验失败")

    source_anchor_timestamp = extract_anchor_timestamp(buffer)
    target_anchor_timestamp = build_target_timestamp(source_anchor_timestamp, mode, target_datetime_text)
    timestamp_delta = target_anchor_timestamp - source_anchor_timestamp

    position = header_size
    definitions: dict[int, MessageDefinition] = {}
    previous_timestamps: dict[int, int] = {}

    while position < data_end:
        header_position = position
        header = buffer[position]
        position += 1

        if header & 0x80:
            local_number = (header >> 5) & 0x03
            definition = definitions[local_number]
            previous_timestamp = previous_timestamps.get(local_number)
            if previous_timestamp is None:
                raise ValueError("遇到压缩时间戳消息时缺少前序时间戳")
            original_timestamp = resolve_compressed_timestamp(previous_timestamp, header)
            shifted_timestamp = original_timestamp + timestamp_delta
            if shifted_timestamp < 0 or shifted_timestamp > 0xFFFFFFFF:
                raise ValueError("复制后的时间戳超出 FIT 支持范围")
            buffer[header_position] = 0x80 | (local_number << 5) | (shifted_timestamp & 0x1F)
            previous_timestamps[local_number] = original_timestamp
            position += sum(field.size for field in definition.fields)
            continue

        if header & 0x40:
            definition, position = parse_definition(buffer, position, header)
            definitions[definition.local_number] = definition
            continue

        local_number = header & 0x0F
        definition = definitions[local_number]
        data_start = position

        for field in definition.fields:
            field_start = data_start + field.offset
            if field.number == 253:
                original_timestamp = read_unsigned(buffer, field_start, field.size, definition.endian)
                if original_timestamp not in INVALID_VALUES[field.size]:
                    previous_timestamps[local_number] = original_timestamp

            if not should_patch_field(definition.global_number, field):
                continue

            original_value = read_unsigned(buffer, field_start, field.size, definition.endian)
            if original_value in INVALID_VALUES[field.size]:
                continue
            shifted_value = original_value + timestamp_delta
            if shifted_value < 0 or shifted_value > 0xFFFFFFFF:
                raise ValueError("复制后的时间戳超出 FIT 支持范围")
            write_unsigned(buffer, field_start, field.size, definition.endian, shifted_value)

        position += sum(field.size for field in definition.fields)

    struct.pack_into("<H", buffer, header_size - 2, crc16(buffer[: header_size - 2]))
    struct.pack_into("<H", buffer, len(buffer) - 2, crc16(buffer[:-2]))
    output_path.write_bytes(buffer)

    return fit_to_datetime(source_anchor_timestamp), fit_to_datetime(target_anchor_timestamp)


def build_default_output_path(source_path: Path) -> Path:
    suffix = datetime.now().date().isoformat()
    return source_path.with_name(f"{source_path.stem}_{suffix}{source_path.suffix}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="源 FIT 文件路径")
    parser.add_argument("-o", "--output", help="输出 FIT 文件路径")
    parser.add_argument("--target-datetime", help="指定目标本地时间，格式为 YYYY-MM-DD HH:MM:SS")
    parser.add_argument(
        "--mode",
        choices=("today", "now"),
        default="today",
        help="today 表示保留原始时分秒，只替换为今天日期；now 表示直接替换为当前时刻；如果传入 --target-datetime，则优先使用指定时间",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = normalize_path(args.source)
    if not source_path.exists():
        raise FileNotFoundError(f"找不到源文件: {args.source}")
    output_path = normalize_path(args.output) if args.output else build_default_output_path(source_path)

    source_anchor, target_anchor = clone_fit_with_shift(
        source_path,
        output_path,
        args.mode,
        args.target_datetime,
    )
    print(f"源文件: {source_path}")
    print(f"输出文件: {output_path}")
    print(f"原始开始时间: {source_anchor.astimezone().isoformat()}")
    print(f"复制后开始时间: {target_anchor.astimezone().isoformat()}")


if __name__ == "__main__":
    main()
