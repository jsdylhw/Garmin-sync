from __future__ import annotations

from math import floor

from fit_activity_transformer.domain.route import RouteModel
from fit_activity_transformer.transform.transform_config import TransformConfig


class TimelineScaler:
    """目标时间轴生成器。

    用途：
    - 根据原路线总时长和速度倍率，生成新的目标 elapsed 时间序列
    """

    def build_target_elapsed_seconds(self, route: RouteModel, config: TransformConfig) -> list[float]:
        """构建目标 elapsed 秒数列表。

        Args:
            route: 原始路线模型。
            config: 变换配置。

        Returns:
            list[float]: 目标时间轴上的 elapsed 秒数序列。
        """

        config.validate()
        if not route.points:
            return []

        scaled_duration_s = route.total_duration_s / config.speed_multiplier
        interval_s = 1.0 / config.target_frequency_hz
        step_count = max(int(floor(scaled_duration_s / interval_s)), 0)
        elapsed_seconds = [round(step * interval_s, 6) for step in range(step_count + 1)]
        if not elapsed_seconds or elapsed_seconds[-1] < scaled_duration_s:
            elapsed_seconds.append(round(scaled_duration_s, 6))
        return elapsed_seconds
