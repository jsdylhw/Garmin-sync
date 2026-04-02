from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from fit_activity_transformer.domain.route import RouteLookupResult, RouteModel
from fit_activity_transformer.gps.interpolation import Interpolator
from fit_activity_transformer.gps.progress_locator import ProgressLocator
from fit_activity_transformer.transform.distance_scheduler import DistanceSchedulePoint


@dataclass
class ResampledTrackPoint:
    """重采样后的轨迹点。

    用途：
    - 保存新时间轴下的时间、位置、海拔、速度与来源区间信息
    """

    timestamp: str | None
    elapsed_seconds: float
    distance_m: float
    latitude: float
    longitude: float
    altitude_m: float | None
    speed_mps: float | None
    source_elapsed_seconds: float
    source_left_index: int
    source_right_index: int
    distance_ratio: float


class GpsResampler:
    """GPS 与海拔重采样器。

    用途：
    - 根据 Step4 的距离调度结果，在原路线中回查并插值生成新的轨迹点
    """

    def __init__(
        self,
        locator: ProgressLocator | None = None,
        interpolator: Interpolator | None = None,
    ) -> None:
        """初始化重采样器。

        Args:
            locator: 距离定位器。
            interpolator: 数值插值工具。
        """

        self.locator = locator or ProgressLocator()
        self.interpolator = interpolator or Interpolator()

    def resample(
        self,
        route: RouteModel,
        schedule: list[DistanceSchedulePoint],
    ) -> list[ResampledTrackPoint]:
        """根据距离调度结果生成新的轨迹点列表。

        Args:
            route: 原始路线模型。
            schedule: Step4 生成的距离调度序列。

        Returns:
            list[ResampledTrackPoint]: 新时间轴下的轨迹点列表。
        """

        if not route.points or not schedule:
            return []

        lookups = self.locator.locate_for_schedule(route, schedule)
        return [self._merge(route, schedule_item, lookup) for schedule_item, lookup in zip(schedule, lookups)]

    def _merge(
        self,
        route: RouteModel,
        schedule_item: DistanceSchedulePoint,
        lookup: RouteLookupResult,
    ) -> ResampledTrackPoint:
        """将单个调度点与单个路线查找结果合并成重采样轨迹点。"""

        timestamp = None
        if route.start_time is not None:
            timestamp = (route.start_time + timedelta(seconds=schedule_item.target_elapsed_seconds)).isoformat()

        left_point = route.points[lookup.left_index]
        right_point = route.points[lookup.right_index]
        altitude_m = self.interpolator.interpolate_optional(left_point.altitude_m, right_point.altitude_m, lookup.ratio)
        speed_mps = schedule_item.scaled_speed_mps

        return ResampledTrackPoint(
            timestamp=timestamp,
            elapsed_seconds=schedule_item.target_elapsed_seconds,
            distance_m=schedule_item.distance_m,
            latitude=lookup.latitude,
            longitude=lookup.longitude,
            altitude_m=altitude_m,
            speed_mps=speed_mps,
            source_elapsed_seconds=schedule_item.source_elapsed_seconds,
            source_left_index=lookup.left_index,
            source_right_index=lookup.right_index,
            distance_ratio=lookup.ratio,
        )
