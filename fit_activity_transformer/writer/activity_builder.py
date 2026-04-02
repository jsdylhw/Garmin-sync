from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean

from fit_activity_transformer.domain.activity import ActivityMetadata, ActivityModel
from fit_activity_transformer.gps.gps_resampler import ResampledTrackPoint


@dataclass
class BuiltRecord:
    """表示即将写回 FIT 的单条记录。

    参数:
        timestamp: 记录时间。
        latitude: 纬度，单位为度。
        longitude: 经度，单位为度。
        distance_m: 累计距离，单位为米。
        altitude_m: 海拔，单位为米。
        speed_mps: 速度，单位为米每秒。
    """

    timestamp: datetime
    latitude: float
    longitude: float
    distance_m: float
    altitude_m: float | None
    speed_mps: float | None


@dataclass
class BuiltLap:
    """表示导出 FIT 时写入的 lap 摘要。

    参数:
        start_time: lap 开始时间。
        end_time: lap 结束时间。
        total_elapsed_time_s: lap 总经过时长，单位秒。
        total_timer_time_s: lap 计时器时长，单位秒。
        total_distance_m: lap 总距离，单位米。
        avg_speed_mps: lap 平均速度，单位米每秒。
        max_speed_mps: lap 最大速度，单位米每秒。
    """

    start_time: datetime
    end_time: datetime
    total_elapsed_time_s: float
    total_timer_time_s: float
    total_distance_m: float
    avg_speed_mps: float | None
    max_speed_mps: float | None


@dataclass
class BuiltSession:
    """表示导出 FIT 时写入的 session 摘要。

    参数:
        start_time: session 开始时间。
        end_time: session 结束时间。
        total_elapsed_time_s: session 总经过时长，单位秒。
        total_timer_time_s: session 计时器时长，单位秒。
        total_distance_m: session 总距离，单位米。
        avg_speed_mps: session 平均速度，单位米每秒。
        max_speed_mps: session 最大速度，单位米每秒。
        total_ascent_m: 累计爬升，单位米。
        total_descent_m: 累计下降，单位米。
    """

    start_time: datetime
    end_time: datetime
    total_elapsed_time_s: float
    total_timer_time_s: float
    total_distance_m: float
    avg_speed_mps: float | None
    max_speed_mps: float | None
    total_ascent_m: float | None = None
    total_descent_m: float | None = None


@dataclass
class BuiltActivity:
    """表示 Step6 导出阶段的完整活动对象。

    参数:
        metadata: 活动元数据。
        records: 准备写出的记录点列表。
        lap: 导出的 lap 信息。
        session: 导出的 session 信息。
        local_timestamp: 活动本地开始时间。
    """

    metadata: ActivityMetadata
    records: list[BuiltRecord] = field(default_factory=list)
    lap: BuiltLap | None = None
    session: BuiltSession | None = None
    local_timestamp: datetime | None = None


class FitActivityBuilder:
    """把重采样轨迹转换为 FIT 写出阶段所需的数据结构。"""

    def build(self, source_activity: ActivityModel, resampled_points: list[ResampledTrackPoint]) -> BuiltActivity:
        """根据源活动和重采样结果构建导出活动。

        参数:
            source_activity: 原始 FIT 映射得到的活动对象。
            resampled_points: Step5 产生的重采样轨迹点。

        返回:
            可直接交给写出器的活动对象。
        """

        if not resampled_points:
            raise ValueError("重采样轨迹为空，无法构建活动")

        records = [
            BuiltRecord(
                timestamp=datetime.fromisoformat(point.timestamp) if point.timestamp else source_activity.metadata.start_time,
                latitude=point.latitude,
                longitude=point.longitude,
                distance_m=point.distance_m,
                altitude_m=point.altitude_m,
                speed_mps=point.speed_mps,
            )
            for point in resampled_points
            if point.timestamp is not None
        ]
        if not records:
            raise ValueError("重采样轨迹缺少有效时间戳")

        start_time = records[0].timestamp
        end_time = records[-1].timestamp
        total_elapsed_time_s = (end_time - start_time).total_seconds()
        total_distance_m = records[-1].distance_m
        speeds = [record.speed_mps for record in records if record.speed_mps is not None]
        altitudes = [record.altitude_m for record in records if record.altitude_m is not None]

        lap = BuiltLap(
            start_time=start_time,
            end_time=end_time,
            total_elapsed_time_s=total_elapsed_time_s,
            total_timer_time_s=total_elapsed_time_s,
            total_distance_m=total_distance_m,
            avg_speed_mps=mean(speeds) if speeds else None,
            max_speed_mps=max(speeds) if speeds else None,
        )
        session = BuiltSession(
            start_time=start_time,
            end_time=end_time,
            total_elapsed_time_s=total_elapsed_time_s,
            total_timer_time_s=total_elapsed_time_s,
            total_distance_m=total_distance_m,
            avg_speed_mps=mean(speeds) if speeds else None,
            max_speed_mps=max(speeds) if speeds else None,
            total_ascent_m=self._calculate_total_ascent(altitudes),
            total_descent_m=self._calculate_total_descent(altitudes),
        )

        metadata = ActivityMetadata(
            file_type=source_activity.metadata.file_type,
            manufacturer=source_activity.metadata.manufacturer,
            product=source_activity.metadata.product,
            serial_number=source_activity.metadata.serial_number,
            time_created=end_time,
            sport=source_activity.metadata.sport,
            sub_sport=source_activity.metadata.sub_sport,
            start_time=start_time,
            local_start_time=start_time,
        )
        return BuiltActivity(
            metadata=metadata,
            records=records,
            lap=lap,
            session=session,
            local_timestamp=start_time,
        )

    def _calculate_total_ascent(self, altitudes: list[float | None]) -> float | None:
        """计算轨迹累计爬升。

        参数:
            altitudes: 轨迹海拔序列。

        返回:
            累计爬升米数；若数据不足则返回 None。
        """

        numeric = [alt for alt in altitudes if alt is not None]
        if len(numeric) < 2:
            return None
        return sum(max(current - previous, 0.0) for previous, current in zip(numeric, numeric[1:]))

    def _calculate_total_descent(self, altitudes: list[float | None]) -> float | None:
        """计算轨迹累计下降。

        参数:
            altitudes: 轨迹海拔序列。

        返回:
            累计下降米数；若数据不足则返回 None。
        """

        numeric = [alt for alt in altitudes if alt is not None]
        if len(numeric) < 2:
            return None
        return sum(max(previous - current, 0.0) for previous, current in zip(numeric, numeric[1:]))
