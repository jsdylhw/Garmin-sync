from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timezone

from fit_activity_transformer.writer.activity_builder import BuiltActivity, BuiltLap, BuiltRecord, BuiltSession


FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)
SEMICIRCLES_PER_DEGREE = 2147483648 / 180


@dataclass
class FieldSpec:
    """描述写出某个 FIT 字段时所需的定义信息。

    参数:
        number: 字段编号。
        size: 字段字节长度。
        base_type: FIT 基础类型编号。
    """

    number: int
    size: int
    base_type: int


class FitMessageBuilder:
    """负责把导出活动对象编码成 FIT 消息字节流。"""

    def build_messages(self, activity: BuiltActivity) -> bytes:
        """按 FIT 协议顺序拼装所有定义消息和数据消息。

        参数:
            activity: 待写出的活动对象。

        返回:
            不含文件头与文件 CRC 的 FIT 数据区字节。
        """

        payload = bytearray()
        payload.extend(self._definition_message(0, 0, self._file_id_fields()))
        payload.extend(self._file_id_message(activity))
        payload.extend(self._definition_message(1, 20, self._record_fields()))
        for record in activity.records:
            payload.extend(self._record_message(record))
        if activity.lap is not None:
            payload.extend(self._definition_message(2, 19, self._lap_fields()))
            payload.extend(self._lap_message(activity.lap))
        if activity.session is not None:
            payload.extend(self._definition_message(3, 18, self._session_fields()))
            payload.extend(self._session_message(activity.session))
        payload.extend(self._definition_message(4, 34, self._activity_fields()))
        payload.extend(self._activity_message(activity))
        return bytes(payload)

    def _definition_message(self, local_number: int, global_number: int, fields: list[FieldSpec]) -> bytes:
        """构造 definition message。

        参数:
            local_number: 本地消息编号。
            global_number: 全局消息编号。
            fields: 当前消息包含的字段定义列表。

        返回:
            对应的 definition message 字节。
        """

        payload = bytearray()
        payload.append(0x40 | local_number)
        payload.append(0)
        payload.append(0)
        payload.extend(struct.pack("<H", global_number))
        payload.append(len(fields))
        for field in fields:
            payload.extend(bytes((field.number, field.size, field.base_type)))
        return bytes(payload)

    def _file_id_fields(self) -> list[FieldSpec]:
        """返回 file_id 消息的字段定义列表。"""

        return [
            FieldSpec(3, 4, 140),
            FieldSpec(4, 4, 134),
            FieldSpec(1, 2, 132),
            FieldSpec(2, 2, 132),
            FieldSpec(0, 1, 0),
        ]

    def _record_fields(self) -> list[FieldSpec]:
        """返回 record 消息的字段定义列表。"""

        return [
            FieldSpec(253, 4, 134),
            FieldSpec(0, 4, 133),
            FieldSpec(1, 4, 133),
            FieldSpec(5, 4, 134),
            FieldSpec(73, 4, 134),
            FieldSpec(78, 4, 134),
        ]

    def _lap_fields(self) -> list[FieldSpec]:
        """返回 lap 消息的字段定义列表。"""

        return [
            FieldSpec(2, 4, 134),
            FieldSpec(7, 4, 134),
            FieldSpec(8, 4, 134),
            FieldSpec(9, 4, 134),
            FieldSpec(110, 4, 134),
            FieldSpec(111, 4, 134),
        ]

    def _session_fields(self) -> list[FieldSpec]:
        """返回 session 消息的字段定义列表。"""

        return [
            FieldSpec(2, 4, 134),
            FieldSpec(7, 4, 134),
            FieldSpec(8, 4, 134),
            FieldSpec(9, 4, 134),
            FieldSpec(22, 2, 132),
            FieldSpec(23, 2, 132),
            FieldSpec(124, 4, 134),
            FieldSpec(125, 4, 134),
        ]

    def _activity_fields(self) -> list[FieldSpec]:
        """返回 activity 消息的字段定义列表。"""

        return [
            FieldSpec(0, 4, 134),
            FieldSpec(1, 2, 132),
            FieldSpec(2, 1, 0),
            FieldSpec(3, 1, 0),
            FieldSpec(4, 1, 0),
            FieldSpec(5, 4, 134),
        ]

    def _file_id_message(self, activity: BuiltActivity) -> bytes:
        """编码 file_id 数据消息。

        参数:
            activity: 待写出的活动对象。

        返回:
            file_id 消息字节。
        """

        metadata = activity.metadata
        payload = bytearray()
        payload.append(0x00)
        payload.extend(struct.pack("<I", metadata.serial_number or 0))
        payload.extend(struct.pack("<I", self._to_fit_timestamp(metadata.time_created or activity.records[-1].timestamp)))
        payload.extend(struct.pack("<H", metadata.manufacturer or 1))
        payload.extend(struct.pack("<H", metadata.product or 0))
        payload.append(metadata.file_type or 4)
        return bytes(payload)

    def _record_message(self, record: BuiltRecord) -> bytes:
        """编码单条 record 数据消息。

        参数:
            record: 待写出的单条记录。

        返回:
            record 消息字节。
        """

        payload = bytearray()
        payload.append(0x01)
        payload.extend(struct.pack("<I", self._to_fit_timestamp(record.timestamp)))
        payload.extend(struct.pack("<i", self._to_semicircles(record.latitude)))
        payload.extend(struct.pack("<i", self._to_semicircles(record.longitude)))
        payload.extend(struct.pack("<I", self._to_distance_raw(record.distance_m)))
        payload.extend(struct.pack("<I", self._to_altitude_raw(record.altitude_m)))
        payload.extend(struct.pack("<I", self._to_speed_raw(record.speed_mps)))
        return bytes(payload)

    def _lap_message(self, lap: BuiltLap) -> bytes:
        """编码 lap 数据消息。

        参数:
            lap: 待写出的 lap 摘要。

        返回:
            lap 消息字节。
        """

        payload = bytearray()
        payload.append(0x02)
        payload.extend(struct.pack("<I", self._to_fit_timestamp(lap.start_time)))
        payload.extend(struct.pack("<I", self._to_duration_raw(lap.total_elapsed_time_s)))
        payload.extend(struct.pack("<I", self._to_duration_raw(lap.total_timer_time_s)))
        payload.extend(struct.pack("<I", self._to_distance_raw(lap.total_distance_m)))
        payload.extend(struct.pack("<I", self._to_speed_raw(lap.avg_speed_mps)))
        payload.extend(struct.pack("<I", self._to_speed_raw(lap.max_speed_mps)))
        return bytes(payload)

    def _session_message(self, session: BuiltSession) -> bytes:
        """编码 session 数据消息。

        参数:
            session: 待写出的 session 摘要。

        返回:
            session 消息字节。
        """

        payload = bytearray()
        payload.append(0x03)
        payload.extend(struct.pack("<I", self._to_fit_timestamp(session.start_time)))
        payload.extend(struct.pack("<I", self._to_duration_raw(session.total_elapsed_time_s)))
        payload.extend(struct.pack("<I", self._to_duration_raw(session.total_timer_time_s)))
        payload.extend(struct.pack("<I", self._to_distance_raw(session.total_distance_m)))
        payload.extend(struct.pack("<H", self._to_uint16(session.total_ascent_m)))
        payload.extend(struct.pack("<H", self._to_uint16(session.total_descent_m)))
        payload.extend(struct.pack("<I", self._to_speed_raw(session.avg_speed_mps)))
        payload.extend(struct.pack("<I", self._to_speed_raw(session.max_speed_mps)))
        return bytes(payload)

    def _activity_message(self, activity: BuiltActivity) -> bytes:
        """编码 activity 结束消息。

        参数:
            activity: 待写出的活动对象。

        返回:
            activity 消息字节。
        """

        session = activity.session
        payload = bytearray()
        payload.append(0x04)
        payload.extend(struct.pack("<I", self._to_duration_raw(session.total_timer_time_s if session else 0.0)))
        payload.extend(struct.pack("<H", 1))
        payload.append(0)
        payload.append(26)
        payload.append(1)
        payload.extend(struct.pack("<I", self._to_fit_timestamp(activity.local_timestamp or activity.records[0].timestamp)))
        return bytes(payload)

    def _to_fit_timestamp(self, value: datetime) -> int:
        """把时间对象转换为 FIT epoch 秒数。

        参数:
            value: 时间对象。

        返回:
            相对 FIT epoch 的整数秒数。
        """

        return int((value.astimezone(timezone.utc) - FIT_EPOCH).total_seconds())

    def _to_semicircles(self, degrees: float) -> int:
        """把经纬度角度值转换为 FIT 半圆坐标。

        参数:
            degrees: 经纬度角度值。

        返回:
            FIT 半圆整数值。
        """

        return int(round(degrees * SEMICIRCLES_PER_DEGREE))

    def _to_distance_raw(self, distance_m: float | None) -> int:
        """把米制距离转换为 FIT 原始整数值。

        参数:
            distance_m: 米制距离。

        返回:
            FIT record 使用的原始距离值。
        """

        if distance_m is None:
            return 0
        return max(int(round(distance_m * 100)), 0)

    def _to_altitude_raw(self, altitude_m: float | None) -> int:
        """把米制海拔转换为 FIT 原始整数值。

        参数:
            altitude_m: 米制海拔。

        返回:
            FIT record 使用的原始海拔值。
        """

        if altitude_m is None:
            return 0xFFFFFFFF
        return max(int(round((altitude_m + 500) * 5)), 0)

    def _to_speed_raw(self, speed_mps: float | None) -> int:
        """把米每秒速度转换为 FIT 原始整数值。

        参数:
            speed_mps: 米每秒速度。

        返回:
            FIT record 使用的原始速度值。
        """

        if speed_mps is None:
            return 0
        return max(int(round(speed_mps * 1000)), 0)

    def _to_duration_raw(self, duration_s: float | None) -> int:
        """把秒数转换为 FIT 使用的毫秒整数。

        参数:
            duration_s: 秒数。

        返回:
            毫秒整数值。
        """

        if duration_s is None:
            return 0
        return max(int(round(duration_s * 1000)), 0)

    def _to_uint16(self, value: float | None) -> int:
        """把数值限制到无符号 16 位整数范围。

        参数:
            value: 待转换数值。

        返回:
            0 到 65535 之间的整数。
        """

        if value is None:
            return 0
        return max(min(int(round(value)), 0xFFFF), 0)
