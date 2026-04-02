from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PROJECT_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fit_activity_transformer.domain.pause import PauseHandlingConfig, PauseStrategy
from fit_activity_transformer.parser.fit_message_mapper import FitMessageMapper
from fit_activity_transformer.parser.fit_reader import FitReader
from fit_activity_transformer.preprocess.gap_detector import GapDetector
from fit_activity_transformer.preprocess.record_filter import RecordFilter
from fit_activity_transformer.preprocess.timestamp_normalizer import TimestampNormalizer
from fit_normalize_1hz import normalize_fit_to_1hz


def parse_args() -> argparse.Namespace:
    """解析 Step1 预处理演示脚本的命令行参数。

    返回:
        包含输入文件、输出目录与停顿策略配置的参数对象。
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("input_fit", help="输入 FIT 文件路径")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "output"),
        help="输出目录，默认写入 fit_activity_transformer/output",
    )
    parser.add_argument(
        "--pause-strategy",
        choices=[strategy.value for strategy in PauseStrategy],
        default=PauseStrategy.REMOVE.value,
        help="停顿处理策略：remove 表示移除，keep 表示保留，compress 表示压缩为固定间隔",
    )
    parser.add_argument(
        "--compressed-gap-seconds",
        type=float,
        default=5.0,
        help="当 pause-strategy=compress 时，停顿段压缩后的目标间隔秒数",
    )
    return parser.parse_args()


def diff_counter(records) -> dict[str, int]:
    """统计相邻记录之间的时间差分布。

    参数:
        records: 待统计的记录点序列。

    返回:
        时间差到出现次数的映射。
    """

    if len(records) < 2:
        return {}
    diffs = []
    for previous_record, current_record in zip(records, records[1:]):
        if previous_record.timestamp is None or current_record.timestamp is None:
            continue
        diffs.append((current_record.timestamp - previous_record.timestamp).total_seconds())
    counts = Counter(diffs)
    return {str(key): value for key, value in sorted(counts.items(), key=lambda item: float(item[0]))}


def records_to_rows(records) -> list[dict]:
    """把记录点对象转换为便于导出 CSV 的行数据。

    参数:
        records: 记录点序列。

    返回:
        适合写入 CSV 的字典列表。
    """

    if not records:
        return []
    start_time = records[0].timestamp
    rows = []
    previous_timestamp = None
    for record in records:
        elapsed_seconds = None
        gap_from_previous = None
        if start_time and record.timestamp:
            elapsed_seconds = (record.timestamp - start_time).total_seconds()
        if previous_timestamp and record.timestamp:
            gap_from_previous = (record.timestamp - previous_timestamp).total_seconds()
        rows.append(
            {
                "timestamp": record.timestamp.isoformat() if record.timestamp else None,
                "elapsed_seconds": elapsed_seconds,
                "gap_from_previous_seconds": gap_from_previous,
                "distance_m": record.distance_m,
                "speed_mps": record.enhanced_speed_mps if record.enhanced_speed_mps is not None else record.speed_mps,
                "heart_rate": record.heart_rate,
                "power": record.power,
                "latitude": record.position_lat,
                "longitude": record.position_long,
            }
        )
        previous_timestamp = record.timestamp
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    """将行数据写入 CSV 文件。

    参数:
        path: 输出文件路径。
        rows: 待写入的行数据。
    """

    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict) -> None:
    """将字典写入 JSON 文件。

    参数:
        path: 输出文件路径。
        payload: 待写入的字典数据。
    """

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    """执行 Step1：过滤记录、识别停顿并做时间归一化。"""

    args = parse_args()
    input_path = Path(args.input_fit)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    reader = FitReader()
    mapper = FitMessageMapper()
    record_filter = RecordFilter()
    gap_detector = GapDetector()
    timestamp_normalizer = TimestampNormalizer()
    pause_config = PauseHandlingConfig(
        strategy=PauseStrategy(args.pause_strategy),
        compressed_gap_seconds=args.compressed_gap_seconds,
    )

    messages = reader.read_file(input_path)
    activity = mapper.map_messages_to_activity(messages)
    filtered_records = record_filter.filter_records_for_timeline(activity.records)
    pauses = gap_detector.detect_pauses(filtered_records)
    normalization = timestamp_normalizer.normalize_records(filtered_records, pauses, pause_config)

    base_name = input_path.stem
    pause_report_path = output_dir / f"{base_name}_step1_pause_report.json"
    normalized_csv_path = output_dir / f"{base_name}_step1_normalized_records.csv"
    summary_path = output_dir / f"{base_name}_step1_summary.json"
    normalized_fit_path = output_dir / f"{base_name}_step1_1hz.fit"

    pause_report = {
        "pause_count": len(pauses),
        "pause_segments": [asdict(pause) for pause in pauses],
    }
    for segment in pause_report["pause_segments"]:
        segment["start_time"] = segment["start_time"].isoformat()
        segment["end_time"] = segment["end_time"].isoformat()

    summary = {
        "message_count": len(messages),
        "original_record_count": len(activity.records),
        "filtered_record_count": len(filtered_records),
        "pause_count": len(pauses),
        "pause_strategy": normalization.summary.strategy,
        "compressed_gap_seconds": args.compressed_gap_seconds,
        "removed_seconds": normalization.summary.removed_seconds,
        "original_diff_counts": diff_counter(filtered_records),
        "normalized_diff_counts": diff_counter(normalization.records),
        "first_pause": pause_report["pause_segments"][0] if pause_report["pause_segments"] else None,
    }

    write_json(pause_report_path, pause_report)
    write_json(summary_path, summary)
    write_csv(normalized_csv_path, records_to_rows(normalization.records))

    binary_record_count = None
    gap_count = None
    removed_seconds = None
    if pause_config.strategy == PauseStrategy.REMOVE:
        binary_record_count, gap_count, removed_seconds = normalize_fit_to_1hz(input_path, normalized_fit_path)

    print(f"消息数量: {len(messages)}")
    print(f"原始 record 数量: {len(activity.records)}")
    print(f"有效 record 数量: {len(filtered_records)}")
    print(f"检测到的停顿段数量: {len(pauses)}")
    print(f"停顿策略: {normalization.summary.strategy}")
    print(f"移除的总停顿秒数: {normalization.summary.removed_seconds}")
    print(f"原始时间差统计: {summary['original_diff_counts']}")
    print(f"归一化后时间差统计: {summary['normalized_diff_counts']}")
    print(f"停顿报告: {pause_report_path}")
    print(f"归一化 CSV: {normalized_csv_path}")
    print(f"摘要 JSON: {summary_path}")
    if pause_config.strategy == PauseStrategy.REMOVE:
        print(f"归一化 FIT: {normalized_fit_path}")
        print(f"二进制改写统计: record={binary_record_count}, gaps={gap_count}, removed_seconds={removed_seconds}")


if __name__ == "__main__":
    main()
