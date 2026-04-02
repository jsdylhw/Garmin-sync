from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PauseStrategy(str, Enum):
    """停顿处理策略枚举。

    - REMOVE: 将停顿尽量移除
    - KEEP: 保留原始停顿
    - COMPRESS: 将停顿压缩到固定秒数
    """

    REMOVE = "remove"
    KEEP = "keep"
    COMPRESS = "compress"


@dataclass
class PauseHandlingConfig:
    """停顿处理配置。

    Attributes:
        strategy: 停顿处理策略。
        compressed_gap_seconds: 当策略为 compress 时使用的压缩秒数。
    """

    strategy: PauseStrategy = PauseStrategy.REMOVE
    compressed_gap_seconds: float = 5.0


@dataclass
class PauseSegment:
    """单个停顿段的结构化表示。

    用途：
    - 记录一次停顿的起止时间
    - 为后续时间轴归一化和停顿策略处理提供基础数据
    """

    start_time: datetime
    end_time: datetime
    gap_seconds: float
    removed_seconds: int
    start_distance_m: float | None = None
    end_distance_m: float | None = None
    start_latitude: float | None = None
    start_longitude: float | None = None
    end_latitude: float | None = None
    end_longitude: float | None = None


@dataclass
class TimestampNormalizationSummary:
    """时间戳归一化结果摘要。"""

    original_record_count: int
    normalized_record_count: int
    pause_count: int
    removed_seconds: float
    strategy: str
