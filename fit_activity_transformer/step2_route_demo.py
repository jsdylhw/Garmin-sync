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
from fit_activity_transformer.route.route_index import RouteIndexer


def parse_args() -> argparse.Namespace:
    """解析 Step2 路线抽象演示脚本的命令行参数。

    返回:
        包含输入文件、输出目录与停顿策略的参数对象。
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


def build_html(summary: dict, route_rows: list[dict], sample_rows: list[dict]) -> str:
    """生成 Step2 演示所需的 HTML 页面。

    参数:
        summary: 路线摘要数据。
        route_rows: 原始路线点列表。
        sample_rows: 按距离采样后的结果列表。

    返回:
        HTML 字符串。
    """

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>Step2 路线抽象演示</title>
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
  <h1>Step2 路线抽象演示</h1>
  <div class="summary">
    <div class="metric"><div class="metric-label">路线点数量</div><div class="metric-value">{summary.get("route_point_count")}</div></div>
    <div class="metric"><div class="metric-label">总距离</div><div class="metric-value">{summary.get("total_distance_m")}</div></div>
    <div class="metric"><div class="metric-label">总时长</div><div class="metric-value">{summary.get("total_duration_s")}</div></div>
    <div class="metric"><div class="metric-label">采样点数量</div><div class="metric-value">{summary.get("sample_count")}</div></div>
  </div>
  <div class="grid">
    <div class="card"><h2>路线轨迹</h2><svg id="routeChart"></svg></div>
    <div class="card"><h2>距离-海拔</h2><svg id="altitudeChart"></svg></div>
    <div class="card"><h2>距离采样点</h2><svg id="sampleChart"></svg></div>
    <div class="card"><h2>摘要</h2><pre id="summaryBlock"></pre></div>
  </div>
  <script>
    const summary = {json.dumps(summary, ensure_ascii=False)};
    const routeRows = {json.dumps(route_rows, ensure_ascii=False)};
    const sampleRows = {json.dumps(sample_rows, ensure_ascii=False)};
    document.getElementById("summaryBlock").textContent = JSON.stringify(summary, null, 2);

    function polylineChart(svgId, rows, xField, yField, color) {{
      const svg = document.getElementById(svgId);
      const points = rows.filter(item => item[xField] !== null && item[yField] !== null);
      if (!points.length) {{
        svg.innerHTML = '<text x="20" y="30" fill="#6b7280">没有可用数据</text>';
        return;
      }}
      const width = svg.clientWidth || 600;
      const height = svg.clientHeight || 280;
      const padding = 20;
      const xs = points.map(item => item[xField]);
      const ys = points.map(item => item[yField]);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const scaleX = value => padding + ((value - minX) / Math.max(maxX - minX, 1e-9)) * (width - padding * 2);
      const scaleY = value => height - padding - ((value - minY) / Math.max(maxY - minY, 1e-9)) * (height - padding * 2);
      const polyline = points.map(item => `${{scaleX(item[xField])}},${{scaleY(item[yField])}}`).join(' ');
      svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
      svg.innerHTML = `<polyline fill="none" stroke="${{color}}" stroke-width="2" points="${{polyline}}"></polyline>`;
    }}

    function routeChart() {{
      const svg = document.getElementById("routeChart");
      const points = routeRows.filter(item => item.longitude !== null && item.latitude !== null);
      if (!points.length) {{
        svg.innerHTML = '<text x="20" y="30" fill="#6b7280">没有 GPS 数据</text>';
        return;
      }}
      const width = svg.clientWidth || 600;
      const height = svg.clientHeight || 280;
      const padding = 20;
      const xs = points.map(item => item.longitude);
      const ys = points.map(item => item.latitude);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const scaleX = value => padding + ((value - minX) / Math.max(maxX - minX, 1e-9)) * (width - padding * 2);
      const scaleY = value => height - padding - ((value - minY) / Math.max(maxY - minY, 1e-9)) * (height - padding * 2);
      const routePolyline = points.map(item => `${{scaleX(item.longitude)}},${{scaleY(item.latitude)}}`).join(' ');
      const samplePolyline = sampleRows.map(item => `${{scaleX(item.longitude)}},${{scaleY(item.latitude)}}`).join(' ');
      svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
      svg.innerHTML = `
        <polyline fill="none" stroke="#2563eb" stroke-width="2" points="${{routePolyline}}"></polyline>
        <polyline fill="none" stroke="#ef4444" stroke-width="1.5" stroke-dasharray="4 4" points="${{samplePolyline}}"></polyline>
      `;
    }}

    routeChart();
    polylineChart("altitudeChart", routeRows, "distance_m", "altitude_m", "#10b981");
    polylineChart("sampleChart", sampleRows, "target_distance_m", "altitude_m", "#f97316");
  </script>
</body>
</html>
"""


def main() -> None:
    """执行 Step2：构建路线模型并输出采样结果。"""

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
    route_indexer = RouteIndexer()
    pause_config = PauseHandlingConfig(
        strategy=PauseStrategy(args.pause_strategy),
        compressed_gap_seconds=args.compressed_gap_seconds,
    )

    messages = reader.read_file(input_path)
    activity = mapper.map_messages_to_activity(messages)
    filtered_records = record_filter.filter_records_for_timeline(activity.records)
    pauses = gap_detector.detect_pauses(filtered_records)
    normalization = timestamp_normalizer.normalize_records(filtered_records, pauses, pause_config)
    route_ready_records = route_cleaner.clean_records(normalization.records)
    route = route_builder.build_from_records(route_ready_records)

    sample_count = min(200, len(route.points))
    sample_rows: list[dict] = []
    if sample_count > 0 and route.total_distance_m > 0:
        target_distances = [route.total_distance_m * index / (sample_count - 1) for index in range(sample_count)]
        sample_rows = [
            {
                "target_distance_m": sample.target_distance_m,
                "left_index": sample.left_index,
                "right_index": sample.right_index,
                "ratio": sample.ratio,
                "latitude": sample.latitude,
                "longitude": sample.longitude,
                "altitude_m": sample.altitude_m,
                "speed_mps": sample.speed_mps,
            }
            for sample in route_indexer.sample_distances(route, target_distances)
        ]

    route_rows = [
        {
            "timestamp": point.timestamp.isoformat(),
            "elapsed_seconds": point.elapsed_seconds,
            "distance_m": point.distance_m,
            "latitude": point.latitude,
            "longitude": point.longitude,
            "altitude_m": point.altitude_m,
            "speed_mps": point.speed_mps,
            "source_index": point.source_index,
        }
        for point in route.points
    ]

    summary = {
        "route_point_count": len(route.points),
        "total_distance_m": route.total_distance_m,
        "total_duration_s": route.total_duration_s,
        "start_time": route.start_time.isoformat() if route.start_time else None,
        "end_time": route.end_time.isoformat() if route.end_time else None,
        "pause_strategy": normalization.summary.strategy,
        "removed_seconds": normalization.summary.removed_seconds,
        "sample_count": len(sample_rows),
        "first_route_point": route_rows[0] if route_rows else None,
        "last_route_point": route_rows[-1] if route_rows else None,
        "first_sample": sample_rows[0] if sample_rows else None,
    }

    base_name = input_path.stem
    summary_path = output_dir / f"{base_name}_step2_route_summary.json"
    route_csv_path = output_dir / f"{base_name}_step2_route_points.csv"
    sample_csv_path = output_dir / f"{base_name}_step2_route_samples.csv"
    html_path = output_dir / f"{base_name}_step2_route_demo.html"

    write_json(summary_path, summary)
    write_csv(route_csv_path, route_rows)
    write_csv(sample_csv_path, sample_rows)
    html_path.write_text(build_html(summary, route_rows, sample_rows), encoding="utf-8")

    print(f"路线点数量: {len(route.points)}")
    print(f"路线总距离: {route.total_distance_m}")
    print(f"路线总时长: {route.total_duration_s}")
    print(f"停顿策略: {normalization.summary.strategy}")
    print(f"移除的总停顿秒数: {normalization.summary.removed_seconds}")
    print(f"距离采样点数量: {len(sample_rows)}")
    print(f"摘要文件: {summary_path}")
    print(f"路线 CSV: {route_csv_path}")
    print(f"采样 CSV: {sample_csv_path}")
    print(f"演示 HTML: {html_path}")


if __name__ == "__main__":
    main()
