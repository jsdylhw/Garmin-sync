from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TransformConfig:
    """时间轴与速度变换配置。

    Attributes:
        speed_multiplier: 速度倍率，决定目标时长缩短比例。
        target_frequency_hz: 目标时间轴采样频率。
    """

    speed_multiplier: float = 1.5
    target_frequency_hz: float = 1.0

    def validate(self) -> None:
        """校验变换配置是否合法。"""

        if self.speed_multiplier <= 0:
            raise ValueError("speed_multiplier 必须大于 0")
        if self.target_frequency_hz <= 0:
            raise ValueError("target_frequency_hz 必须大于 0")
