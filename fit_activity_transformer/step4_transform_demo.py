from __future__ import annotations

import argparse
import csv
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
from fit_activity_transformer.route.route_builder import RouteBuilder
from fit_activity_transformer.route.route_cleaner import RouteCleaner
from fit_activity_transformer.transform.distance_scheduler import DistanceScheduler
from fit_activity_transformer.transform.speed_transformer import SpeedTransformer
from fit_activity_transformer.transform.timeline_scaler import TimelineScaler
from fit_activity_transformer.transform.transform_config import TransformConfig


def parse_args() -> argparse.Namespace:
    """解析 Step4 时间轴变换演示脚本的命令行参数。

    返回:
        包含输入文件、速度倍率、停顿策略和输出目录的参数对象。
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("input_fit", help="输入 FIT 文件路径")
    parser.add_argument("--speed-multiplier", type=float, default=1.5, help="速度倍率，例如 1.5")
    parser.add_argument(
        "--pause-strategy",
        choices=[strategy.value for strategy in PauseStrategy],
        default=PauseStrategy.REMOVE.value,
        help="停顿处理策略：remove / keep / compress",
    )
    parser.add_argument("--compressed-gap-seconds", type=float, default=5.0, help="compress 策略压缩后的停顿秒数")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "output"),
        help="输出目录，默认写入 fit_activity_transformer/output",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict) -> None:
    """将字典写入 JSON 文件。

    参数:
        path: 输出文件路径。
        payload: 待写入数据。
    """

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    """将行数据写入 CSV 文件。

    参数:
        path: 输出文件路径。
        rows: 待写入的行数据列表。
    """

    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_html(summary: dict, source_rows: list[dict], schedule_rows: list[dict]) -> str:
    """生成 Step4 演示页面。

    参数:
        summary: 变换摘要数据。
        source_rows: 原始路线曲线数据。
        schedule_rows: 目标距离调度数据。

    返回:
        HTML 字符串。
    """

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>Step4 时间轴与速度变换演示</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f7f8fb; color: #1f2937; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 12px; margin-bottom: 16px; }}
    .metric {{ background: white; border-radius: 10px; padding: 14px; box-shadow: 0 2px 10px rgba(0,0,0,0.06); }}
    .metric-label {{ font-size: 12px; color: #6b7280; margin-bottom: 6px; }}
    .metric-value {{ font-size: 18px; font-weight: 600; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(320px, 1fr)); gap: 16px; }}
    .card {{ background: white; border-radius: 10px; padding: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.06); }}
    svg {{ width: 100%; height: 280px; background: #fcfcfd; border: 1px solid #e5e7eb; border-radius: 8px; }}
    pre {{ white-space: pre-wrap; word-break: break-word; font-size: 12px; background: #111827; color: #e5e7eb; padding: 12px; border-radius: 8px; overflow: auto; }}
  </style>
</head>
<body>
  <h1>Step4 时间轴与速度变换演示</h1>
  <div class="summary">
    <div class="metric"><div class="metric-label">速度倍率</div><div class="metric-value">{summary.get("speed_multiplier")}</div></div>
    <div class="metric"><div class="metric-label">原始时长</div><div class="metric-value">{summary.get("source_duration_s")}</div></div>
    <div class="metric"><div class="metric-label">目标时长</div><div class="metric-value">{summary.get("target_duration_s")}</div></div>
    <div class="metric"><div class="metric-label">调度点数量</div><div class="metric-value">{summary.get("schedule_count")}</div></div>
  </div>
  <div class="grid">
    <div class="card"><h2>时间-距离对比</h2><svg id="distanceChart"></svg></div>
    <div class="card"><h2>时间-速度对比</h2><svg id="speedChart"></svg></div>
    <div class="card"><h2>目标调度距离-速度</h2><svg id="scheduleChart"></svg></div>
    <div class="card"><h2>摘要</h2><pre id="summaryBlock"></pre></div>
  </div>
  <script>
    const summary = {json.dumps(summary, ensure_ascii=False)};
    const sourceRows = {json.dumps(source_rows, ensure_ascii=False)};
    const scheduleRows = {json.dumps(schedule_rows, ensure_ascii=False)};
    document.getElementById("summaryBlock").textContent = JSON.stringify(summary, null, 2);

    function lineChart(svgId, series, xField, yField) {{
      const svg = document.getElementById(svgId);
      const width = svg.clientWidth || 600;
      const height = svg.clientHeight || 280;
      const padding = 20;
      const allPoints = series.flatMap(item => item.rows.filter(row => row[xField] !== null && row[yField] !== null));
      if (!allPoints.length) {{
        svg.innerHTML = '<text x="20" y="30" fill="#6b7280">没有可用数据</text>';
        return;
      }}
      const xs = allPoints.map(item => item[xField]);
      const ys = allPoints.map(item => item[yField]);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const scaleX = value => padding + ((value - minX) / Math.max(maxX - minX, 1e-9)) * (width - padding * 2);
      const scaleY = value => height - padding - ((value - minY) / Math.max(maxY - minY, 1e-9)) * (height - padding * 2);
      svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
      svg.innerHTML = series.map(item => {{
        const polyline = item.rows
          .filter(row => row[xField] !== null && row[yField] !== null)
          .map(row => `${{scaleX(row[xField])}},${{scaleY(row[yField])}}`)
          .join(' ');
        return `<polyline fill="none" stroke="${{item.color}}" stroke-width="2" points="${{polyline}}"></polyline>`;
      }}).join('');
    }}

    lineChart("distanceChart", [
      {{ rows: sourceRows, color: "#2563eb" }},
      {{ rows: scheduleRows, color: "#ef4444" }}
    ], "elapsed_seconds", "distance_m");

    lineChart("speedChart", [
      {{ rows: sourceRows, color: "#2563eb" }},
      {{ rows: scheduleRows, color: "#ef4444" }}
    ], "elapsed_seconds", "speed_mps");

    lineChart("scheduleChart", [
      {{ rows: scheduleRows, color: "#10b981" }}
    ], "distance_m", "speed_mps");
  </script>
</body>
</html>
"""


def main() -> None:
    """执行 Step4：速度倍率变换与目标距离调度。"""

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
    speed_transformer = SpeedTransformer()
    distance_scheduler = DistanceScheduler()

    pause_config = PauseHandlingConfig(
        strategy=PauseStrategy(args.pause_strategy),
        compressed_gap_seconds=args.compressed_gap_seconds,
    )
    transform_config = TransformConfig(speed_multiplier=args.speed_multiplier, target_frequency_hz=1.0)

    messages = reader.read_file(input_path)
    activity = mapper.map_messages_to_activity(messages)
    filtered_records = record_filter.filter_records_for_timeline(activity.records)
    pauses = gap_detector.detect_pauses(filtered_records)
    normalization = timestamp_normalizer.normalize_records(filtered_records, pauses, pause_config)
    route_ready_records = route_cleaner.clean_records(normalization.records)
    route = route_builder.build_from_records(route_ready_records)

    target_elapsed_seconds = timeline_scaler.build_target_elapsed_seconds(route, transform_config)
    distance_schedule = distance_scheduler.build_distance_schedule(route, target_elapsed_seconds, transform_config)
    scaled_source_speeds = speed_transformer.scale_route_speeds(route, transform_config)

    source_rows = [
        {
            "elapsed_seconds": point.elapsed_seconds,
            "distance_m": point.distance_m,
            "speed_mps": point.speed_mps,
        }
        for point in route.points
    ]
    schedule_rows = [
        {
            "elapsed_seconds": item.target_elapsed_seconds,
            "source_elapsed_seconds": item.source_elapsed_seconds,
            "distance_m": item.distance_m,
            "speed_mps": item.scaled_speed_mps,
            "source_left_index": item.source_left_index,
            "source_right_index": item.source_right_index,
            "ratio": item.ratio,
        }
        for item in distance_schedule
    ]

    summary = {
        "pause_strategy": normalization.summary.strategy,
        "removed_seconds": normalization.summary.removed_seconds,
        "speed_multiplier": args.speed_multiplier,
        "source_duration_s": route.total_duration_s,
        "target_duration_s": target_elapsed_seconds[-1] if target_elapsed_seconds else 0.0,
        "source_distance_m": route.total_distance_m,
        "target_distance_m": distance_schedule[-1].distance_m if distance_schedule else 0.0,
        "schedule_count": len(distance_schedule),
        "source_speed_example": scaled_source_speeds[:5],
        "first_schedule_point": schedule_rows[0] if schedule_rows else None,
        "last_schedule_point": schedule_rows[-1] if schedule_rows else None,
    }

    base_name = input_path.stem
    summary_path = output_dir / f"{base_name}_step4_transform_summary.json"
    source_csv_path = output_dir / f"{base_name}_step4_source_curve.csv"
    schedule_csv_path = output_dir / f"{base_name}_step4_distance_schedule.csv"
    html_path = output_dir / f"{base_name}_step4_transform_demo.html"

    write_json(summary_path, summary)
    write_csv(source_csv_path, source_rows)
    write_csv(schedule_csv_path, schedule_rows)
    html_path.write_text(build_html(summary, source_rows, schedule_rows), encoding="utf-8")

    print(f"停顿策略: {normalization.summary.strategy}")
    print(f"速度倍率: {args.speed_multiplier}")
    print(f"原始时长: {route.total_duration_s}")
    print(f"目标时长: {summary['target_duration_s']}")
    print(f"原始距离: {route.total_distance_m}")
    print(f"目标距离: {summary['target_distance_m']}")
    print(f"调度点数量: {len(distance_schedule)}")
    print(f"摘要文件: {summary_path}")
    print(f"源曲线 CSV: {source_csv_path}")
    print(f"调度 CSV: {schedule_csv_path}")
    print(f"演示 HTML: {html_path}")


if __name__ == "__main__":
    main()
