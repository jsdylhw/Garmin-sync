from __future__ import annotations

from fit_activity_transformer.domain.route import RouteLookupResult, RouteModel
from fit_activity_transformer.route.route_index import RouteIndexer
from fit_activity_transformer.transform.distance_scheduler import DistanceSchedulePoint


class ProgressLocator:
    """按距离调度结果定位原路线区间。"""

    def __init__(self, route_indexer: RouteIndexer | None = None) -> None:
        """初始化定位器。

        Args:
            route_indexer: 可选的路线索引器；为空时自动创建默认实现。
        """

        self.route_indexer = route_indexer or RouteIndexer()

    def locate_for_schedule(
        self,
        route: RouteModel,
        schedule: list[DistanceSchedulePoint],
    ) -> list[RouteLookupResult]:
        """为整条距离调度序列批量定位原路线区间。

        Args:
            route: 原始路线模型。
            schedule: Step4 生成的距离调度序列。

        Returns:
            list[RouteLookupResult]: 与 schedule 一一对应的定位结果。
        """

        return [self.route_indexer.locate_by_distance(route, item.distance_m) for item in schedule]
