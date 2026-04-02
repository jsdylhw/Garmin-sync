from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fit_activity_transformer.domain.pause import PauseHandlingConfig, PauseStrategy
from fit_activity_transformer.gps.gps_resampler import GpsResampler
from fit_activity_transformer.parser.fit_message_mapper import FitMessageMapper
from fit_activity_transformer.parser.fit_reader import FitReader
from fit_activity_transformer.preprocess.gap_detector import GapDetector
from fit_activity_transformer.preprocess.record_filter import RecordFilter
from fit_activity_transformer.preprocess.timestamp_normalizer import TimestampNormalizer
from fit_activity_transformer.route.route_builder import RouteBuilder
from fit_activity_transformer.route.route_cleaner import RouteCleaner
from fit_activity_transformer.transform.distance_scheduler import DistanceScheduler
from fit_activity_transformer.transform.timeline_scaler import TimelineScaler
from fit_activity_transformer.transform.transform_config import TransformConfig
from fit_activity_transformer.writer.activity_builder import FitActivityBuilder
from fit_activity_transformer.writer.fit_writer import FitWriter


def parse_args() -> argparse.Namespace:
    """解析 Step6 FIT 导出演示脚本的命令行参数。

    返回:
        包含输入文件、速度倍率、停顿策略和输出目录的参数对象。
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("input_fit", help="输入 FIT 文件路径")
    parser.add_argument("--speed-multiplier", type=float, default=1.5, help="速度倍率，例如 1.5")
    parser.add_argument(
        "--pause-strategy",
        choices=[strategy.value for strategy in PauseStrategy],
        default=PauseStrategy.COMPRESS.value,
        help="停顿处理策略：remove / keep / compress",
    )
    parser.add_argument("--compressed-gap-seconds", type=float, default=5.0, help="compress 策略压缩后的停顿秒数")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "output"),
        help="输出目录，默认写入 fit_activity_transformer/output",
    )
    return parser.parse_args()


def main() -> None:
    """执行 Step6：重采样后构建新活动并写出新的 FIT 文件。"""

    args = parse_args()
    input_path = Path(args.input_fit)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    reader = FitReader()
    mapper = FitMessageMapper()
    record_filter = RecordFilter()
    gap_detector = GapDetector()
    timestamp_normalizer = TimestampNormalizer()
    route_cleaner = RouteCleaner()
    route_builder = RouteBuilder()
    timeline_scaler = TimelineScaler()
    distance_scheduler = DistanceScheduler()
    gps_resampler = GpsResampler()
    activity_builder = FitActivityBuilder()
    fit_writer = FitWriter()

    pause_config = PauseHandlingConfig(
        strategy=PauseStrategy(args.pause_strategy),
        compressed_gap_seconds=args.compressed_gap_seconds,
    )
    transform_config = TransformConfig(speed_multiplier=args.speed_multiplier, target_frequency_hz=1.0)

    messages = reader.read_file(input_path)
    source_activity = mapper.map_messages_to_activity(messages)
    filtered_records = record_filter.filter_records_for_timeline(source_activity.records)
    pauses = gap_detector.detect_pauses(filtered_records)
    normalization = timestamp_normalizer.normalize_records(filtered_records, pauses, pause_config)
    route_ready_records = route_cleaner.clean_records(normalization.records)
    route = route_builder.build_from_records(route_ready_records)
    target_elapsed_seconds = timeline_scaler.build_target_elapsed_seconds(route, transform_config)
    schedule = distance_scheduler.build_distance_schedule(route, target_elapsed_seconds, transform_config)
    resampled_points = gps_resampler.resample(route, schedule)

    built_activity = activity_builder.build(source_activity, resampled_points)
    output_fit_path = output_dir / f"{input_path.stem}_step6_transformed.fit"
    fit_writer.write(built_activity, output_fit_path)

    reloaded_messages = reader.read_file(output_fit_path)
    reloaded_activity = mapper.map_messages_to_activity(reloaded_messages)
    output_summary = mapper.summarize_activity(reloaded_activity)
    summary = {
        "input_fit": str(input_path),
        "output_fit": str(output_fit_path),
        "pause_strategy": pause_config.strategy.value,
        "compressed_gap_seconds": pause_config.compressed_gap_seconds,
        "speed_multiplier": args.speed_multiplier,
        "source_record_count": len(source_activity.records),
        "resampled_point_count": len(resampled_points),
        "output_record_count": len(reloaded_activity.records),
        "output_lap_count": len(reloaded_activity.laps),
        "output_session_present": reloaded_activity.session is not None,
        "output_summary": output_summary,
    }

    summary_path = output_dir / f"{input_path.stem}_step6_fit_writer_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"输出 FIT: {output_fit_path}")
    print(f"摘要文件: {summary_path}")
    print(f"输出记录点数量: {len(reloaded_activity.records)}")
    print(f"输出 lap 数量: {len(reloaded_activity.laps)}")
    print(f"输出 session 存在: {reloaded_activity.session is not None}")
    print(f"第一条记录时间: {output_summary['first_record_time']}")
    print(f"最后一条记录时间: {output_summary['last_record_time']}")
    print(f"最后距离: {output_summary['last_record_distance_m']}")


if __name__ == "__main__":
    main()
