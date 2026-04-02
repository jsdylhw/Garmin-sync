from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RoutePoint:
    """路线点模型。

    用途：
    - 将 record 记录转成可按距离采样的路线节点
    - 保存时间、距离、经纬度、海拔、速度等基础信息
    """

    timestamp: datetime
    elapsed_seconds: float
    distance_m: float
    latitude: float
    longitude: float
    altitude_m: float | None = None
    speed_mps: float | None = None
    source_index: int | None = None


@dataclass
class RouteModel:
    """路线整体模型。

    用途：
    - 聚合所有路线点
    - 保存路线的总距离、总时长与起止时间
    """

    points: list[RoutePoint] = field(default_factory=list)
    total_distance_m: float = 0.0
    total_duration_s: float = 0.0
    start_time: datetime | None = None
    end_time: datetime | None = None


@dataclass
class RouteLookupResult:
    """按距离查找路线后得到的插值结果。"""

    left_index: int
    right_index: int
    ratio: float
    target_distance_m: float
    latitude: float
    longitude: float
    altitude_m: float | None = None
    speed_mps: float | None = None
