from __future__ import annotations

import argparse
import struct
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fit_clone_current_date import (
    INVALID_VALUES,
    PATCHABLE_FIELDS,
    crc16,
    normalize_path,
    parse_definition,
    read_unsigned,
    resolve_compressed_timestamp,
    write_unsigned,
)


DURATION_FIELDS = {
    18: {7, 8},
    19: {7, 8},
    34: {0},
}


@dataclass
class Gap:
    previous_timestamp: int
    next_timestamp: int
    removed_seconds: int


def validate_fit(buffer: bytes | bytearray) -> tuple[int, int]:
    if buffer[8:12] != b".FIT":
        raise ValueError("输入文件不是合法的 FIT 文件")
    header_size = buffer[0]
    data_size = struct.unpack_from("<I", buffer, 4)[0]
    stored_header_crc = struct.unpack_from("<H", buffer, header_size - 2)[0]
    if stored_header_crc != crc16(buffer[: header_size - 2]):
        raise ValueError("FIT 文件头 CRC 校验失败")
    stored_file_crc = struct.unpack_from("<H", buffer, len(buffer) - 2)[0]
    if stored_file_crc != crc16(buffer[:-2]):
        raise ValueError("FIT 文件 CRC 校验失败")
    return header_size, header_size + data_size


def collect_record_timestamps(buffer: bytes | bytearray, data_start: int, data_end: int) -> list[int]:
    position = data_start
    definitions = {}
    previous_timestamps: dict[int, int] = {}
    record_timestamps: list[int] = []

    while position < data_end:
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
            if definition.global_number == 20:
                record_timestamps.append(current_timestamp)
            position += sum(field.size for field in definition.fields)
            continue

        if header & 0x40:
            definition, position = parse_definition(buffer, position, header)
            definitions[definition.local_number] = definition
            continue

        local_number = header & 0x0F
        definition = definitions[local_number]
        data_position = position
        timestamp_value = None
        for field in definition.fields:
            if field.number == 253 and field.size == 4:
                value = read_unsigned(buffer, data_position + field.offset, field.size, definition.endian)
                if value not in INVALID_VALUES[field.size]:
                    timestamp_value = value
                    previous_timestamps[local_number] = value
            position += field.size
        if definition.global_number == 20 and timestamp_value is not None:
            record_timestamps.append(timestamp_value)

    if not record_timestamps:
        raise ValueError("未找到 record 消息，无法归一化为 1Hz")
    return record_timestamps


def build_gap_model(record_timestamps: list[int]) -> tuple[list[int], list[int], list[Gap]]:
    new_timestamps = [record_timestamps[0]]
    gaps: list[Gap] = []
    for previous_timestamp, current_timestamp in zip(record_timestamps, record_timestamps[1:]):
        if current_timestamp <= previous_timestamp:
            raise ValueError("record 时间戳不是严格递增，无法归一化")
        if current_timestamp - previous_timestamp > 1:
            gaps.append(
                Gap(
                    previous_timestamp=previous_timestamp,
                    next_timestamp=current_timestamp,
                    removed_seconds=current_timestamp - previous_timestamp - 1,
                )
            )
        new_timestamps.append(new_timestamps[-1] + 1)
    return record_timestamps, new_timestamps, gaps


def removed_seconds_before(timestamp: int, gaps: list[Gap]) -> int:
    removed = 0
    for gap in gaps:
        if timestamp <= gap.previous_timestamp:
            break
        progress_in_gap = min(timestamp - gap.previous_timestamp - 1, gap.removed_seconds)
        if progress_in_gap > 0:
            removed += progress_in_gap
        if timestamp < gap.next_timestamp:
            break
    return removed


def remap_timestamp(timestamp: int, gaps: list[Gap]) -> int:
    return timestamp - removed_seconds_before(timestamp, gaps)


def remap_duration(start_timestamp: int, raw_duration_ms: int, gaps: list[Gap]) -> int:
    end_timestamp = start_timestamp + raw_duration_ms / 1000
    removed_start = removed_seconds_before(int(start_timestamp), gaps)
    removed_end = removed_seconds_before(int(end_timestamp), gaps)
    new_duration_ms = int(round(raw_duration_ms - (removed_end - removed_start) * 1000))
    return max(new_duration_ms, 0)


def normalize_fit_to_1hz(source_path: Path, output_path: Path) -> tuple[int, int, int]:
    buffer = bytearray(source_path.read_bytes())
    data_start, data_end = validate_fit(buffer)
    record_timestamps = collect_record_timestamps(buffer, data_start, data_end)
    _, _, gaps = build_gap_model(record_timestamps)

    position = data_start
    definitions = {}
    previous_original_timestamps: dict[int, int] = {}

    while position < data_end:
        header_position = position
        header = buffer[position]
        position += 1

        if header & 0x80:
            local_number = (header >> 5) & 0x03
            definition = definitions[local_number]
            previous_original = previous_original_timestamps.get(local_number)
            if previous_original is None:
                raise ValueError("遇到压缩时间戳消息时缺少前序时间戳")
            original_timestamp = resolve_compressed_timestamp(previous_original, header)
            new_timestamp = remap_timestamp(original_timestamp, gaps)
            buffer[header_position] = 0x80 | (local_number << 5) | (new_timestamp & 0x1F)
            previous_original_timestamps[local_number] = original_timestamp
            position += sum(field.size for field in definition.fields)
            continue

        if header & 0x40:
            definition, position = parse_definition(buffer, position, header)
            definitions[definition.local_number] = definition
            continue

        local_number = header & 0x0F
        definition = definitions[local_number]
        data_position = position
        message_timestamp = None

        for field in definition.fields:
            field_start = data_position + field.offset
            if field.size not in INVALID_VALUES:
                continue

            raw_value = read_unsigned(buffer, field_start, field.size, definition.endian)
            if raw_value in INVALID_VALUES[field.size]:
                continue

            if field.number == 253 and field.size == 4:
                message_timestamp = raw_value
                previous_original_timestamps[local_number] = raw_value

            if field.number in PATCHABLE_FIELDS.get(definition.global_number, set()) and field.size == 4:
                new_value = remap_timestamp(raw_value, gaps)
                write_unsigned(buffer, field_start, field.size, definition.endian, new_value)
                continue

            if field.number in DURATION_FIELDS.get(definition.global_number, set()) and field.size == 4:
                anchor_timestamp = message_timestamp
                if anchor_timestamp is None and definition.global_number in {18, 19}:
                    start_field = next((item for item in definition.fields if item.number == 2 and item.size == 4), None)
                    if start_field is not None:
                        anchor_timestamp = read_unsigned(buffer, data_position + start_field.offset, 4, definition.endian)
                if anchor_timestamp is not None:
                    new_duration = remap_duration(anchor_timestamp, raw_value, gaps)
                    write_unsigned(buffer, field_start, field.size, definition.endian, new_duration)

        position += sum(field.size for field in definition.fields)

    struct.pack_into("<H", buffer, data_start - 2, crc16(buffer[: data_start - 2]))
    struct.pack_into("<H", buffer, len(buffer) - 2, crc16(buffer[:-2]))
    output_path.write_bytes(buffer)
    removed_seconds = sum(gap.removed_seconds for gap in gaps)
    return len(record_timestamps), len(gaps), removed_seconds


def build_default_output_path(source_path: Path) -> Path:
    return source_path.with_name(f"{source_path.stem}_1hz{source_path.suffix}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="源 FIT 文件路径")
    parser.add_argument("-o", "--output", help="输出 FIT 文件路径")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = normalize_path(args.source)
    if not source_path.exists():
        raise FileNotFoundError(f"找不到源文件: {args.source}")
    output_path = normalize_path(args.output) if args.output else build_default_output_path(source_path)
    record_count, gap_count, removed_seconds = normalize_fit_to_1hz(source_path, output_path)
    print(f"源文件: {source_path}")
    print(f"输出文件: {output_path}")
    print(f"record 数量: {record_count}")
    print(f"压缩的停顿段数量: {gap_count}")
    print(f"移除的总停顿秒数: {removed_seconds}")


if __name__ == "__main__":
    main()
