from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fit_activity_transformer.domain.activity import (
    ActivityMetadata,
    ActivityModel,
    LapSummary,
    RecordPoint,
    SessionSummary,
)
from fit_activity_transformer.parser.fit_reader import FitMessage


FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)
SEMICIRCLE_TO_DEGREES = 180 / 2147483648

FILE_ID_FIELDS = {
    0: "file_type",
    1: "manufacturer",
    2: "product",
    3: "serial_number",
    4: "time_created",
}

SESSION_FIELDS = {
    2: "start_time",
    7: "total_elapsed_time_s",
    8: "total_timer_time_s",
    9: "total_distance_m",
    14: "avg_speed_mps",
    15: "max_speed_mps",
    16: "avg_heart_rate",
    17: "max_heart_rate",
    20: "avg_power",
    21: "max_power",
    22: "total_ascent_m",
    23: "total_descent_m",
    124: "enhanced_avg_speed_mps",
    125: "enhanced_max_speed_mps",
}

LAP_FIELDS = {
    2: "start_time",
    7: "total_elapsed_time_s",
    8: "total_timer_time_s",
    9: "total_distance_m",
    13: "avg_speed_mps",
    14: "max_speed_mps",
    15: "avg_heart_rate",
    16: "max_heart_rate",
    19: "avg_power",
    20: "max_power",
    110: "enhanced_avg_speed_mps",
    111: "enhanced_max_speed_mps",
}

ACTIVITY_FIELDS = {
    0: "total_timer_time_s",
    1: "num_sessions",
    2: "type",
    3: "event",
    4: "event_type",
    5: "local_timestamp",
}

RECORD_FIELDS = {
    253: "timestamp",
    0: "position_lat",
    1: "position_long",
    2: "altitude_m",
    3: "heart_rate",
    4: "cadence",
    5: "distance_m",
    6: "speed_mps",
    7: "power",
    13: "temperature_c",
    29: "accumulated_power",
    73: "enhanced_altitude_m",
    78: "enhanced_speed_mps",
}


class FitMessageMapper:
    """将底层 FIT 消息映射为业务层活动模型。"""

    def map_messages_to_activity(self, messages: list[FitMessage]) -> ActivityModel:
        """把消息列表聚合成完整的活动对象。

        参数:
            messages: 按文件顺序解析得到的 FIT 消息列表。

        返回:
            包含 metadata、records、laps、session 的活动模型。
        """

        metadata = ActivityMetadata()
        records: list[RecordPoint] = []
        laps: list[LapSummary] = []
        session: SessionSummary | None = None
        activity_fields: dict[str, Any] = {}

        for message in messages:
            if message.global_number == 0:
                metadata = self._merge_metadata(metadata, message)
            elif message.global_number == 18:
                session = self._map_session(message)
                if session.start_time and metadata.start_time is None:
                    metadata.start_time = session.start_time
            elif message.global_number == 19:
                laps.append(self._map_lap(message))
            elif message.global_number == 20:
                records.append(self._map_record(message))
            elif message.global_number == 34:
                activity_fields = self._map_fields(message.fields_by_number, ACTIVITY_FIELDS)
                local_timestamp = self._as_timestamp(activity_fields.get("local_timestamp"))
                if local_timestamp is not None:
                    activity_fields["local_timestamp"] = local_timestamp
                    metadata.local_start_time = local_timestamp

        if session and metadata.local_start_time is None and session.start_time is not None:
            metadata.local_start_time = session.start_time

        return ActivityModel(
            metadata=metadata,
            records=records,
            laps=laps,
            session=session,
            activity_fields=activity_fields,
        )

    def summarize_activity(self, activity: ActivityModel) -> dict[str, Any]:
        """生成活动摘要，便于写入 JSON 或命令行展示。

        参数:
            activity: 已完成业务映射的活动对象。

        返回:
            适合序列化的摘要字典。
        """

        records = activity.records
        first_record = records[0] if records else None
        last_record = records[-1] if records else None
        return {
            "metadata": self._serialize_value(asdict(activity.metadata)),
            "record_count": len(records),
            "lap_count": len(activity.laps),
            "session": self._serialize_value(asdict(activity.session)) if activity.session else None,
            "first_record_time": first_record.timestamp.isoformat() if first_record and first_record.timestamp else None,
            "last_record_time": last_record.timestamp.isoformat() if last_record and last_record.timestamp else None,
            "first_record_distance_m": first_record.distance_m if first_record else None,
            "last_record_distance_m": last_record.distance_m if last_record else None,
            "activity_fields": self._serialize_value(activity.activity_fields),
        }

    def records_for_visualization(self, activity: ActivityModel) -> list[dict[str, Any]]:
        """提取可视化所需的逐秒记录字段。

        参数:
            activity: 已完成业务映射的活动对象。

        返回:
            可直接写入 CSV 或前端图表的数据行列表。
        """

        if not activity.records:
            return []
        start_time = activity.records[0].timestamp
        rows: list[dict[str, Any]] = []
        for record in activity.records:
            elapsed_seconds = None
            if start_time and record.timestamp:
                elapsed_seconds = (record.timestamp - start_time).total_seconds()
            rows.append(
                {
                    "timestamp": record.timestamp.isoformat() if record.timestamp else None,
                    "elapsed_seconds": elapsed_seconds,
                    "distance_m": record.distance_m,
                    "speed_mps": self._first_non_none(record.enhanced_speed_mps, record.speed_mps),
                    "altitude_m": self._first_non_none(record.enhanced_altitude_m, record.altitude_m),
                    "heart_rate": record.heart_rate,
                    "power": record.power,
                    "cadence": record.cadence,
                    "latitude": record.position_lat,
                    "longitude": record.position_long,
                }
            )
        return rows

    def _merge_metadata(self, metadata: ActivityMetadata, message: FitMessage) -> ActivityMetadata:
        """把 file_id 消息合并到活动元数据中。

        参数:
            metadata: 当前累计的元数据对象。
            message: file_id 类型的 FIT 消息。

        返回:
            更新后的元数据对象。
        """

        values = self._map_fields(message.fields_by_number, FILE_ID_FIELDS)
        if values.get("time_created") is not None:
            values["time_created"] = self._as_timestamp(values["time_created"])
        for key, value in values.items():
            setattr(metadata, key, value)
        return metadata

    def _map_session(self, message: FitMessage) -> SessionSummary:
        """将 session 消息映射为会话摘要对象。

        参数:
            message: session 类型的 FIT 消息。

        返回:
            会话摘要对象。
        """

        values = self._map_fields(message.fields_by_number, SESSION_FIELDS)
        return SessionSummary(
            start_time=self._as_timestamp(values.get("start_time")),
            total_elapsed_time_s=self._as_seconds(values.get("total_elapsed_time_s")),
            total_timer_time_s=self._as_seconds(values.get("total_timer_time_s")),
            total_distance_m=self._as_distance(values.get("total_distance_m")),
            avg_speed_mps=self._first_non_none(
                self._as_speed(values.get("enhanced_avg_speed_mps")),
                self._as_speed(values.get("avg_speed_mps")),
            ),
            max_speed_mps=self._first_non_none(
                self._as_speed(values.get("enhanced_max_speed_mps")),
                self._as_speed(values.get("max_speed_mps")),
            ),
            avg_heart_rate=self._as_int(values.get("avg_heart_rate")),
            max_heart_rate=self._as_int(values.get("max_heart_rate")),
            avg_power=self._as_int(values.get("avg_power")),
            max_power=self._as_int(values.get("max_power")),
            total_ascent_m=self._as_distance(values.get("total_ascent_m")),
            total_descent_m=self._as_distance(values.get("total_descent_m")),
            raw_fields=values,
        )

    def _map_lap(self, message: FitMessage) -> LapSummary:
        """将 lap 消息映射为圈段摘要对象。

        参数:
            message: lap 类型的 FIT 消息。

        返回:
            圈段摘要对象。
        """

        values = self._map_fields(message.fields_by_number, LAP_FIELDS)
        return LapSummary(
            start_time=self._as_timestamp(values.get("start_time")),
            total_elapsed_time_s=self._as_seconds(values.get("total_elapsed_time_s")),
            total_timer_time_s=self._as_seconds(values.get("total_timer_time_s")),
            total_distance_m=self._as_distance(values.get("total_distance_m")),
            avg_speed_mps=self._first_non_none(
                self._as_speed(values.get("enhanced_avg_speed_mps")),
                self._as_speed(values.get("avg_speed_mps")),
            ),
            max_speed_mps=self._first_non_none(
                self._as_speed(values.get("enhanced_max_speed_mps")),
                self._as_speed(values.get("max_speed_mps")),
            ),
            avg_heart_rate=self._as_int(values.get("avg_heart_rate")),
            max_heart_rate=self._as_int(values.get("max_heart_rate")),
            avg_power=self._as_int(values.get("avg_power")),
            max_power=self._as_int(values.get("max_power")),
            raw_fields=values,
        )

    def _map_record(self, message: FitMessage) -> RecordPoint:
        """将 record 消息映射为逐点记录对象。

        参数:
            message: record 类型的 FIT 消息。

        返回:
            记录点对象。
        """

        values = self._map_fields(message.fields_by_number, RECORD_FIELDS)
        return RecordPoint(
            timestamp=self._as_timestamp(values.get("timestamp")),
            position_lat=self._as_position(values.get("position_lat")),
            position_long=self._as_position(values.get("position_long")),
            altitude_m=self._as_altitude(values.get("altitude_m")),
            enhanced_altitude_m=self._as_enhanced_altitude(values.get("enhanced_altitude_m")),
            distance_m=self._as_distance(values.get("distance_m")),
            speed_mps=self._as_speed(values.get("speed_mps")),
            enhanced_speed_mps=self._as_speed(values.get("enhanced_speed_mps")),
            heart_rate=self._as_int(values.get("heart_rate")),
            cadence=self._as_int(values.get("cadence")),
            power=self._as_int(values.get("power")),
            temperature_c=self._as_int(values.get("temperature_c")),
            accumulated_power=self._as_int(values.get("accumulated_power")),
            raw_fields=values,
        )

    def _map_fields(self, values_by_number: dict[int, Any], fields: dict[int, str]) -> dict[str, Any]:
        """按字段字典把编号映射为具名字段。

        参数:
            values_by_number: 原始字段编号到值的映射。
            fields: 字段编号到业务字段名的映射表。

        返回:
            具名字段字典。
        """

        return {
            field_name: values_by_number[field_number]
            for field_number, field_name in fields.items()
            if field_number in values_by_number
        }

    def _as_position(self, value: Any) -> float | None:
        """将 FIT 半圆坐标转换为经纬度角度值。

        参数:
            value: 原始半圆坐标。

        返回:
            十进制度数；若为空则返回 None。
        """

        if value is None:
            return None
        return float(value) * SEMICIRCLE_TO_DEGREES

    def _as_timestamp(self, value: Any) -> datetime | None:
        """将原始时间值转换为时间对象。

        参数:
            value: datetime 或 FIT epoch 秒数。

        返回:
            UTC 时间对象；若为空则返回 None。
        """

        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return FIT_EPOCH + timedelta(seconds=int(value))

    def _as_altitude(self, value: Any) -> float | None:
        """将标准海拔原始值转换为米。

        参数:
            value: FIT 协议中的原始海拔值。

        返回:
            米制海拔；若为空则返回 None。
        """

        if value is None:
            return None
        return float(value) / 5 - 500

    def _as_enhanced_altitude(self, value: Any) -> float | None:
        """将增强海拔原始值转换为米。

        参数:
            value: FIT 协议中的增强海拔原始值。

        返回:
            米制海拔；若为空则返回 None。
        """

        if value is None:
            return None
        return float(value) / 5 - 500

    def _as_speed(self, value: Any) -> float | None:
        """将原始速度值转换为米每秒。

        参数:
            value: FIT 协议中的原始速度值。

        返回:
            米每秒速度；若为空则返回 None。
        """

        if value is None:
            return None
        return float(value) / 1000

    def _as_distance(self, value: Any) -> float | None:
        """将原始距离值转换为米。

        参数:
            value: FIT 协议中的原始距离值。

        返回:
            米制距离；若为空则返回 None。
        """

        if value is None:
            return None
        return float(value) / 100

    def _as_seconds(self, value: Any) -> float | None:
        """将毫秒制时长转换为秒。

        参数:
            value: FIT 协议中的原始时长值。

        返回:
            秒数；若为空则返回 None。
        """

        if value is None:
            return None
        return float(value) / 1000

    def _as_int(self, value: Any) -> int | None:
        """将数值安全转换为整数。

        参数:
            value: 原始字段值。

        返回:
            整数值；若为空则返回 None。
        """

        if value is None:
            return None
        return int(value)

    def _first_non_none(self, *values: Any) -> Any:
        """返回参数列表中第一个非空值。

        参数:
            *values: 待依次检查的候选值。

        返回:
            第一个非 None 的值；若全部为空则返回 None。
        """

        for value in values:
            if value is not None:
                return value
        return None

    def _serialize_mapping(self, values: dict[str, Any]) -> dict[str, Any]:
        """递归序列化字典中的时间等复杂类型。

        参数:
            values: 待序列化字典。

        返回:
            已转为基础类型的新字典。
        """

        serialized: dict[str, Any] = {}
        for key, value in values.items():
            serialized[key] = self._serialize_value(value)
        return serialized

    def _serialize_value(self, value: Any) -> Any:
        """将单个值递归转换为可 JSON 序列化对象。

        参数:
            value: 待序列化的任意值。

        返回:
            可安全写入 JSON 的基础类型值。
        """

        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, timedelta):
            return value.total_seconds()
        if isinstance(value, dict):
            return {key: self._serialize_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        return value
