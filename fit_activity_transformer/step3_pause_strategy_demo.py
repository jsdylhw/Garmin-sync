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
from fit_activity_transformer.parser.fit_message_mapper import FitMessageMapper
from fit_activity_transformer.parser.fit_reader import FitReader
from fit_activity_transformer.preprocess.gap_detector import GapDetector
from fit_activity_transformer.preprocess.record_filter import RecordFilter
from fit_activity_transformer.preprocess.timestamp_normalizer import TimestampNormalizer


def parse_args() -> argparse.Namespace:
    """解析 Step3 停顿策略演示脚本的命令行参数。

    返回:
        包含输入文件、输出目录和压缩停顿秒数的参数对象。
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("input_fit", help="输入 FIT 文件路径")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "output"),
        help="输出目录，默认写入 fit_activity_transformer/output",
    )
    parser.add_argument(
        "--compressed-gap-seconds",
        type=float,
        default=5.0,
        help="compress 策略下停顿段压缩后的目标间隔秒数",
    )
    return parser.parse_args()


def time_diff_counts(records) -> dict[str, int]:
    """统计记录序列的相邻时间差分布。

    参数:
        records: 待统计的记录点序列。

    返回:
        时间差字符串到出现次数的映射。
    """

    counts: dict[str, int] = {}
    for previous_record, current_record in zip(records, records[1:]):
        if previous_record.timestamp is None or current_record.timestamp is None:
            continue
        diff = (current_record.timestamp - previous_record.timestamp).total_seconds()
        key = f"{diff:.1f}"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: float(item[0])))


def main() -> None:
    """执行 Step3：对比 remove、keep、compress 三种停顿策略。"""

    args = parse_args()
    input_path = Path(args.input_fit)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    reader = FitReader()
    mapper = FitMessageMapper()
    record_filter = RecordFilter()
    gap_detector = GapDetector()
    timestamp_normalizer = TimestampNormalizer()

    messages = reader.read_file(input_path)
    activity = mapper.map_messages_to_activity(messages)
    filtered_records = record_filter.filter_records_for_timeline(activity.records)
    pauses = gap_detector.detect_pauses(filtered_records)

    strategy_results = []
    for strategy in (PauseStrategy.REMOVE, PauseStrategy.KEEP, PauseStrategy.COMPRESS):
        config = PauseHandlingConfig(
            strategy=strategy,
            compressed_gap_seconds=args.compressed_gap_seconds,
        )
        normalization = timestamp_normalizer.normalize_records(filtered_records, pauses, config)
        strategy_results.append(
            {
                "strategy": strategy.value,
                "removed_seconds": normalization.summary.removed_seconds,
                "normalized_record_count": normalization.summary.normalized_record_count,
                "diff_counts": time_diff_counts(normalization.records),
                "first_timestamp": normalization.records[0].timestamp.isoformat() if normalization.records else None,
                "last_timestamp": normalization.records[-1].timestamp.isoformat() if normalization.records else None,
            }
        )

    result = {
        "input_fit": str(input_path),
        "pause_count": len(pauses),
        "compressed_gap_seconds": args.compressed_gap_seconds,
        "strategies": strategy_results,
    }

    output_path = output_dir / f"{input_path.stem}_step3_pause_strategy_summary.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"停顿段数量: {len(pauses)}")
    print(f"结果文件: {output_path}")
    for strategy_result in strategy_results:
        print(
            f"{strategy_result['strategy']}: "
            f"removed_seconds={strategy_result['removed_seconds']}, "
            f"diff_counts={strategy_result['diff_counts']}"
        )


if __name__ == "__main__":
    main()
