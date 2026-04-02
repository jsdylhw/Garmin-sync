from __future__ import annotations

from fit_activity_transformer.domain.route import RouteModel
from fit_activity_transformer.transform.transform_config import TransformConfig


class SpeedTransformer:
    """速度变换器。

    用途：
    - 根据速度倍率生成目标速度序列
    """

    def scale_route_speeds(self, route: RouteModel, config: TransformConfig) -> list[float | None]:
        """按倍率缩放路线速度。

        Args:
            route: 原始路线模型。
            config: 变换配置。

        Returns:
            list[float | None]: 与路线点一一对应的目标速度列表。
        """

        config.validate()
        scaled_speeds: list[float | None] = []
        for point in route.points:
            if point.speed_mps is None:
                scaled_speeds.append(None)
                continue
            scaled_speeds.append(point.speed_mps * config.speed_multiplier)
        return scaled_speeds
