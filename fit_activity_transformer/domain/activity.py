from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ActivityMetadata:
    """活动级元信息。

    用途：
    - 保存 FIT 文件级别的基础属性
    - 作为后续导出新 FIT 时的元信息来源
    """

    file_type: int | None = None
    manufacturer: int | None = None
    product: int | None = None
    serial_number: int | None = None
    time_created: datetime | None = None
    sport: int | None = None
    sub_sport: int | None = None
    start_time: datetime | None = None
    local_start_time: datetime | None = None


@dataclass
class RecordPoint:
    """单条 record 记录的内部表示。

    用途：
    - 承接 FIT record 消息中的原始运动数据
    - 作为预处理、路线抽象和后续变换的基础输入
    """

    timestamp: datetime | None = None
    position_lat: float | None = None
    position_long: float | None = None
    altitude_m: float | None = None
    enhanced_altitude_m: float | None = None
    distance_m: float | None = None
    speed_mps: float | None = None
    enhanced_speed_mps: float | None = None
    heart_rate: int | None = None
    cadence: int | None = None
    power: int | None = None
    temperature_c: int | None = None
    accumulated_power: int | None = None
    raw_fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class LapSummary:
    """单个 lap 的汇总信息。"""

    start_time: datetime | None = None
    total_elapsed_time_s: float | None = None
    total_timer_time_s: float | None = None
    total_distance_m: float | None = None
    avg_speed_mps: float | None = None
    max_speed_mps: float | None = None
    avg_heart_rate: int | None = None
    max_heart_rate: int | None = None
    avg_power: int | None = None
    max_power: int | None = None
    raw_fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionSummary:
    """整次 session 的汇总信息。"""

    start_time: datetime | None = None
    total_elapsed_time_s: float | None = None
    total_timer_time_s: float | None = None
    total_distance_m: float | None = None
    avg_speed_mps: float | None = None
    max_speed_mps: float | None = None
    avg_heart_rate: int | None = None
    max_heart_rate: int | None = None
    avg_power: int | None = None
    max_power: int | None = None
    total_ascent_m: float | None = None
    total_descent_m: float | None = None
    raw_fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActivityModel:
    """整个活动的统一内部模型。

    用途：
    - 聚合 metadata、records、laps、session
    - 作为 parser、preprocess、route、writer 之间的数据中枢
    """

    metadata: ActivityMetadata = field(default_factory=ActivityMetadata)
    records: list[RecordPoint] = field(default_factory=list)
    laps: list[LapSummary] = field(default_factory=list)
    session: SessionSummary | None = None
    activity_fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """将活动模型转成字典。

        Returns:
            dict[str, Any]: 适合序列化或调试输出的字典结构。
        """

        return asdict(self)
