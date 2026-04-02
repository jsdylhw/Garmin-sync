from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_right

from fit_activity_transformer.domain.route import RouteModel
from fit_activity_transformer.transform.transform_config import TransformConfig


@dataclass
class DistanceSchedulePoint:
    """目标时间轴上单个调度点的结构。

    Attributes:
        target_elapsed_seconds: 新时间轴上的 elapsed 秒数。
        source_elapsed_seconds: 映射回原路线后的 elapsed 秒数。
        distance_m: 当前调度点对应的累计距离。
        scaled_speed_mps: 当前调度点对应的目标速度。
        source_left_index: 原路线插值左侧点索引。
        source_right_index: 原路线插值右侧点索引。
        ratio: 左右点之间的插值比例。
    """

    target_elapsed_seconds: float
    source_elapsed_seconds: float
    distance_m: float
    scaled_speed_mps: float | None
    source_left_index: int
    source_right_index: int
    ratio: float


class DistanceScheduler:
    """距离调度器。

    用途：
    - 将目标时间轴映射回原路线时间进度
    - 根据原路线的 elapsed 时间插值得到新的距离推进序列
    """

    def build_distance_schedule(
        self,
        route: RouteModel,
        target_elapsed_seconds: list[float],
        config: TransformConfig,
    ) -> list[DistanceSchedulePoint]:
        """生成目标时间轴上的距离调度序列。

        Args:
            route: 原始路线模型。
            target_elapsed_seconds: Step4 目标时间轴。
            config: 速度变换配置。

        Returns:
            list[DistanceSchedulePoint]: 新时间轴上每个时间点对应的距离和速度信息。
        """

        config.validate()
        if not route.points or not target_elapsed_seconds:
            return []

        source_elapsed = [point.elapsed_seconds for point in route.points]
        schedule: list[DistanceSchedulePoint] = []
        for target_elapsed in target_elapsed_seconds:
            source_time = min(target_elapsed * config.speed_multiplier, route.total_duration_s)
            left_index, right_index, ratio = self._locate_by_elapsed(source_elapsed, source_time)
            left_point = route.points[left_index]
            right_point = route.points[right_index]
            schedule.append(
                DistanceSchedulePoint(
                    target_elapsed_seconds=target_elapsed,
                    source_elapsed_seconds=source_time,
                    distance_m=self._interpolate(left_point.distance_m, right_point.distance_m, ratio),
                    scaled_speed_mps=self._interpolate_optional(left_point.speed_mps, right_point.speed_mps, ratio, config.speed_multiplier),
                    source_left_index=left_index,
                    source_right_index=right_index,
                    ratio=ratio,
                )
            )
        return schedule

    def _locate_by_elapsed(self, source_elapsed: list[float], target_elapsed: float) -> tuple[int, int, float]:
        """在原 elapsed 时间序列中定位目标时间对应的区间。"""

        if target_elapsed <= source_elapsed[0]:
            return 0, 0, 0.0
        if target_elapsed >= source_elapsed[-1]:
            last_index = len(source_elapsed) - 1
            return last_index, last_index, 0.0

        right_index = bisect_right(source_elapsed, target_elapsed)
        left_index = right_index - 1
        left_elapsed = source_elapsed[left_index]
        right_elapsed = source_elapsed[right_index]
        span = right_elapsed - left_elapsed
        ratio = 0.0 if span <= 0 else (target_elapsed - left_elapsed) / span
        return left_index, right_index, ratio

    def _interpolate(self, left_value: float, right_value: float, ratio: float) -> float:
        """对两个数值执行线性插值。"""

        return left_value + (right_value - left_value) * ratio

    def _interpolate_optional(
        self,
        left_value: float | None,
        right_value: float | None,
        ratio: float,
        speed_multiplier: float,
    ) -> float | None:
        """对可选速度数值插值并应用速度倍率。"""

        if left_value is None and right_value is None:
            return None
        if left_value is None:
            return right_value * speed_multiplier if right_value is not None else None
        if right_value is None:
            return left_value * speed_multiplier
        return self._interpolate(left_value, right_value, ratio) * speed_multiplier
