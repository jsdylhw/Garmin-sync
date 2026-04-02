from __future__ import annotations

from fit_activity_transformer.domain.activity import RecordPoint


class RouteCleaner:
    """路线记录清洗器。

    用途：
    - 去除无法参与路线抽象的记录
    - 保证后续按距离采样时数据单调、可用
    """

    def clean_records(self, records: list[RecordPoint]) -> list[RecordPoint]:
        """清洗构建路线前的记录列表。

        Args:
            records: 预处理后的记录列表。

        Returns:
            list[RecordPoint]: 过滤掉无时间戳、无坐标、无距离或距离倒退的记录。
        """

        cleaned: list[RecordPoint] = []
        last_distance = None

        for record in records:
            if record.timestamp is None:
                continue
            if record.position_lat is None or record.position_long is None:
                continue
            if record.distance_m is None:
                continue
            if last_distance is not None and record.distance_m + 1e-6 < last_distance:
                continue
            cleaned.append(record)
            last_distance = record.distance_m

        return cleaned
