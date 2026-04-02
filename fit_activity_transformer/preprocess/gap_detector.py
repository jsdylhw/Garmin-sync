from __future__ import annotations

from fit_activity_transformer.domain.activity import RecordPoint
from fit_activity_transformer.domain.pause import PauseSegment


class GapDetector:
    """停顿段检测器。

    用途：
    - 根据相邻记录的时间差识别停顿
    - 输出结构化的 PauseSegment 列表
    """

    def detect_pauses(self, records: list[RecordPoint], threshold_seconds: float = 1.0) -> list[PauseSegment]:
        """检测停顿段。

        Args:
            records: 已按时间排序的记录列表。
            threshold_seconds: 超过该时间差即视为停顿。

        Returns:
            list[PauseSegment]: 检测出的停顿段列表。
        """

        pauses: list[PauseSegment] = []
        if len(records) < 2:
            return pauses

        for previous_record, current_record in zip(records, records[1:]):
            if previous_record.timestamp is None or current_record.timestamp is None:
                continue
            gap_seconds = (current_record.timestamp - previous_record.timestamp).total_seconds()
            if gap_seconds <= threshold_seconds:
                continue
            pauses.append(
                PauseSegment(
                    start_time=previous_record.timestamp,
                    end_time=current_record.timestamp,
                    gap_seconds=gap_seconds,
                    removed_seconds=max(int(round(gap_seconds - threshold_seconds)), 0),
                    start_distance_m=previous_record.distance_m,
                    end_distance_m=current_record.distance_m,
                    start_latitude=previous_record.position_lat,
                    start_longitude=previous_record.position_long,
                    end_latitude=current_record.position_lat,
                    end_longitude=current_record.position_long,
                )
            )
        return pauses
