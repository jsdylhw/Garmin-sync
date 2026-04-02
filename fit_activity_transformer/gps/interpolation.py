from __future__ import annotations


class Interpolator:
    """GPS 与海拔插值工具。"""

    def interpolate(self, left_value: float, right_value: float, ratio: float) -> float:
        """对两个数值做线性插值。"""

        return left_value + (right_value - left_value) * ratio

    def interpolate_optional(
        self,
        left_value: float | None,
        right_value: float | None,
        ratio: float,
    ) -> float | None:
        """对可选数值做插值。

        Args:
            left_value: 左侧值。
            right_value: 右侧值。
            ratio: 0 到 1 之间的插值比例。

        Returns:
            float | None: 插值结果；若左右值都为空则返回 None。
        """

        if left_value is None and right_value is None:
            return None
        if left_value is None:
            return right_value
        if right_value is None:
            return left_value
        return self.interpolate(left_value, right_value, ratio)
