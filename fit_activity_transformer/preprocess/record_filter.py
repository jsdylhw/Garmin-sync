from __future__ import annotations

from fit_activity_transformer.domain.activity import RecordPoint


class RecordFilter:
    """record 预过滤器。

    用途：
    - 在进入停顿检测和时间轴归一化前剔除明显无效的记录
    """

    def filter_records_for_timeline(self, records: list[RecordPoint]) -> list[RecordPoint]:
        """过滤可用于时间线处理的记录。

        Args:
            records: 原始 record 列表。

        Returns:
            list[RecordPoint]: 仅保留带时间戳的记录。
        """

        filtered: list[RecordPoint] = []
        for record in records:
            if record.timestamp is None:
                continue
            filtered.append(record)
        return filtered
