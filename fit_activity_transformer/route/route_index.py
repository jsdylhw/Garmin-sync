from __future__ import annotations

from bisect import bisect_right

from fit_activity_transformer.domain.route import RouteLookupResult, RouteModel


class RouteIndexer:
    """路线距离索引器。

    用途：
    - 在给定目标距离时快速定位到相邻路线点
    - 对经纬度、海拔、速度等值进行线性插值
    """

    def locate_by_distance(self, route: RouteModel, target_distance_m: float) -> RouteLookupResult:
        """按目标距离在路线中查找插值结果。

        Args:
            route: 结构化路线模型。
            target_distance_m: 目标累计距离，单位米。

        Returns:
            RouteLookupResult: 包含相邻点索引和插值后位置的结果。
        """

        if not route.points:
            raise ValueError("路线为空，无法按距离查找")

        distances = [point.distance_m for point in route.points]

        if target_distance_m <= distances[0]:
            point = route.points[0]
            return RouteLookupResult(
                left_index=0,
                right_index=0,
                ratio=0.0,
                target_distance_m=target_distance_m,
                latitude=point.latitude,
                longitude=point.longitude,
                altitude_m=point.altitude_m,
                speed_mps=point.speed_mps,
            )

        if target_distance_m >= distances[-1]:
            point = route.points[-1]
            last_index = len(route.points) - 1
            return RouteLookupResult(
                left_index=last_index,
                right_index=last_index,
                ratio=0.0,
                target_distance_m=target_distance_m,
                latitude=point.latitude,
                longitude=point.longitude,
                altitude_m=point.altitude_m,
                speed_mps=point.speed_mps,
            )

        right_index = bisect_right(distances, target_distance_m)
        left_index = right_index - 1
        left_point = route.points[left_index]
        right_point = route.points[right_index]
        segment_distance = right_point.distance_m - left_point.distance_m
        ratio = 0.0 if segment_distance <= 0 else (target_distance_m - left_point.distance_m) / segment_distance

        return RouteLookupResult(
            left_index=left_index,
            right_index=right_index,
            ratio=ratio,
            target_distance_m=target_distance_m,
            latitude=self._interpolate(left_point.latitude, right_point.latitude, ratio),
            longitude=self._interpolate(left_point.longitude, right_point.longitude, ratio),
            altitude_m=self._interpolate_optional(left_point.altitude_m, right_point.altitude_m, ratio),
            speed_mps=self._interpolate_optional(left_point.speed_mps, right_point.speed_mps, ratio),
        )

    def sample_distances(self, route: RouteModel, distance_values: list[float]) -> list[RouteLookupResult]:
        """批量按距离采样路线。"""

        return [self.locate_by_distance(route, distance) for distance in distance_values]

    def _interpolate(self, left_value: float, right_value: float, ratio: float) -> float:
        """对两个数值做线性插值。"""

        return left_value + (right_value - left_value) * ratio

    def _interpolate_optional(self, left_value: float | None, right_value: float | None, ratio: float) -> float | None:
        """对可选数值做线性插值。"""

        if left_value is None and right_value is None:
            return None
        if left_value is None:
            return right_value
        if right_value is None:
            return left_value
        return self._interpolate(left_value, right_value, ratio)
