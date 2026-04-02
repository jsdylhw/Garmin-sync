from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta

from fit_activity_transformer.domain.activity import RecordPoint
from fit_activity_transformer.domain.pause import (
    PauseHandlingConfig,
    PauseSegment,
    PauseStrategy,
    TimestampNormalizationSummary,
)


@dataclass
class TimestampNormalizationResult:
    """时间戳归一化结果。

    Attributes:
        records: 归一化后的记录列表。
        pauses: 检测到的停顿段列表。
        summary: 归一化摘要信息。
    """

    records: list[RecordPoint]
    pauses: list[PauseSegment]
    summary: TimestampNormalizationSummary


class TimestampNormalizer:
    """时间戳归一化器。

    用途：
    - 根据停顿策略调整 record 的时间轴
    - 为后续路线抽象和速度变换提供统一时间线
    """

    def normalize_records(
        self,
        records: list[RecordPoint],
        pauses: list[PauseSegment],
        config: PauseHandlingConfig | None = None,
    ) -> TimestampNormalizationResult:
        """按给定停顿策略归一化记录时间戳。

        Args:
            records: 原始记录列表。
            pauses: 已检测到的停顿段列表。
            config: 停顿处理配置；为空时默认使用 remove。

        Returns:
            TimestampNormalizationResult: 归一化后的记录与摘要。
        """

        config = config or PauseHandlingConfig()
        if not records:
            return TimestampNormalizationResult(
                records=[],
                pauses=pauses,
                summary=TimestampNormalizationSummary(
                    original_record_count=0,
                    normalized_record_count=0,
                    pause_count=0,
                    removed_seconds=0,
                    strategy=config.strategy.value,
                ),
            )

        normalized_records: list[RecordPoint] = []
        removed_seconds = 0.0
        pause_index = 0

        for index, record in enumerate(records):
            cloned_record = deepcopy(record)
            if index == 0:
                normalized_records.append(cloned_record)
                continue

            if record.timestamp is None:
                normalized_records.append(cloned_record)
                continue

            while pause_index < len(pauses) and pauses[pause_index].end_time <= record.timestamp:
                removed_seconds += self._removed_seconds_for_pause(pauses[pause_index], config)
                pause_index += 1

            normalized_timestamp = record.timestamp - timedelta(seconds=removed_seconds)
            if normalized_timestamp <= normalized_records[-1].timestamp:
                normalized_timestamp = normalized_records[-1].timestamp + timedelta(seconds=1)
            cloned_record.timestamp = normalized_timestamp
            normalized_records.append(cloned_record)

        summary = TimestampNormalizationSummary(
            original_record_count=len(records),
            normalized_record_count=len(normalized_records),
            pause_count=len(pauses),
            removed_seconds=sum(self._removed_seconds_for_pause(pause, config) for pause in pauses),
            strategy=config.strategy.value,
        )
        return TimestampNormalizationResult(
            records=normalized_records,
            pauses=pauses,
            summary=summary,
        )

    def normalize_records_to_1hz(self, records: list[RecordPoint], pauses: list[PauseSegment]) -> TimestampNormalizationResult:
        """兼容旧接口，按 remove 策略生成连续 1Hz 时间轴。

        Args:
            records: 原始记录列表。
            pauses: 停顿段列表。

        Returns:
            TimestampNormalizationResult: remove 策略下的归一化结果。
        """

        return self.normalize_records(records, pauses, PauseHandlingConfig(strategy=PauseStrategy.REMOVE))

    def _removed_seconds_for_pause(self, pause: PauseSegment, config: PauseHandlingConfig) -> float:
        """计算单个停顿段在当前策略下需要减少的秒数。"""

        if config.strategy == PauseStrategy.KEEP:
            return 0.0
        if config.strategy == PauseStrategy.COMPRESS:
            target_gap_seconds = max(config.compressed_gap_seconds, 1.0)
            return max(pause.gap_seconds - target_gap_seconds, 0.0)
        return max(pause.gap_seconds - 1.0, 0.0)
