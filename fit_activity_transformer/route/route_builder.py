from __future__ import annotations

from fit_activity_transformer.domain.activity import RecordPoint
from fit_activity_transformer.domain.route import RouteModel, RoutePoint


class RouteBuilder:
    """路线构建器。

    用途：
    - 将 record 列表转换成 RouteModel
    - 为后续按距离查位置和重采样提供统一路线输入
    """

    def build_from_records(self, records: list[RecordPoint]) -> RouteModel:
        """从 record 列表构建路线模型。

        Args:
            records: 已经过滤和归一化的记录列表。

        Returns:
            RouteModel: 结构化后的路线模型。
        """

        if not records:
            return RouteModel()

        start_time = records[0].timestamp
        route_points: list[RoutePoint] = []

        for index, record in enumerate(records):
            if record.timestamp is None or start_time is None:
                continue
            if record.position_lat is None or record.position_long is None or record.distance_m is None:
                continue
            route_points.append(
                RoutePoint(
                    timestamp=record.timestamp,
                    elapsed_seconds=(record.timestamp - start_time).total_seconds(),
                    distance_m=record.distance_m,
                    latitude=record.position_lat,
                    longitude=record.position_long,
                    altitude_m=record.enhanced_altitude_m if record.enhanced_altitude_m is not None else record.altitude_m,
                    speed_mps=record.enhanced_speed_mps if record.enhanced_speed_mps is not None else record.speed_mps,
                    source_index=index,
                )
            )

        if not route_points:
            return RouteModel()

        return RouteModel(
            points=route_points,
            total_distance_m=route_points[-1].distance_m,
            total_duration_s=route_points[-1].elapsed_seconds,
            start_time=route_points[0].timestamp,
            end_time=route_points[-1].timestamp,
        )
