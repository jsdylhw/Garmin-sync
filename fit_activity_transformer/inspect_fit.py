from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fit_activity_transformer.parser.fit_message_mapper import FitMessageMapper
from fit_activity_transformer.parser.fit_reader import FitReader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_fit", help="输入 FIT 文件路径")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "output"),
        help="输出目录，默认写入 fit_activity_transformer/output",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_html(summary: dict, rows: list[dict]) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>FIT 数据可视化</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f7f8fb; color: #1f2937; }}
    h1, h2 {{ margin: 0 0 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(320px, 1fr)); gap: 16px; }}
    .card {{ background: white; border-radius: 12px; padding: 16px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06); }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; margin-bottom: 16px; }}
    .metric {{ background: #eef2ff; padding: 12px; border-radius: 10px; }}
    .metric-label {{ font-size: 12px; color: #4b5563; margin-bottom: 6px; }}
    .metric-value {{ font-size: 18px; font-weight: 600; }}
    svg {{ width: 100%; height: 220px; background: #fcfcfd; border: 1px solid #e5e7eb; border-radius: 8px; }}
    pre {{ white-space: pre-wrap; word-break: break-word; font-size: 12px; background: #111827; color: #e5e7eb; padding: 12px; border-radius: 8px; overflow: auto; }}
  </style>
</head>
<body>
  <h1>FIT 数据可视化</h1>
  <div class="summary">
    <div class="metric"><div class="metric-label">记录点数量</div><div class="metric-value">{summary.get("record_count")}</div></div>
    <div class="metric"><div class="metric-label">Lap 数量</div><div class="metric-value">{summary.get("lap_count")}</div></div>
    <div class="metric"><div class="metric-label">开始时间</div><div class="metric-value">{summary.get("first_record_time") or "-"}</div></div>
    <div class="metric"><div class="metric-label">结束时间</div><div class="metric-value">{summary.get("last_record_time") or "-"}</div></div>
  </div>
  <div class="grid">
    <div class="card"><h2>速度</h2><svg id="speedChart"></svg></div>
    <div class="card"><h2>功率</h2><svg id="powerChart"></svg></div>
    <div class="card"><h2>心率</h2><svg id="heartRateChart"></svg></div>
    <div class="card"><h2>海拔</h2><svg id="altitudeChart"></svg></div>
    <div class="card"><h2>轨迹</h2><svg id="routeChart"></svg></div>
    <div class="card"><h2>摘要</h2><pre id="summaryBlock"></pre></div>
  </div>
  <script>
    const summary = {json.dumps(summary, ensure_ascii=False)};
    const rows = {json.dumps(rows, ensure_ascii=False)};

    document.getElementById("summaryBlock").textContent = JSON.stringify(summary, null, 2);

    function createLineChart(elementId, field, color) {{
      const svg = document.getElementById(elementId);
      const points = rows.filter(item => item.elapsed_seconds !== null && item[field] !== null);
      if (!points.length) {{
        svg.innerHTML = '<text x="20" y="30" fill="#6b7280">没有可用数据</text>';
        return;
      }}
      const width = svg.clientWidth || 500;
      const height = svg.clientHeight || 220;
      const padding = 20;
      const xs = points.map(item => item.elapsed_seconds);
      const ys = points.map(item => item[field]);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const scaleX = value => padding + ((value - minX) / Math.max(maxX - minX, 1)) * (width - padding * 2);
      const scaleY = value => height - padding - ((value - minY) / Math.max(maxY - minY, 1)) * (height - padding * 2);
      const polyline = points.map(item => `${{scaleX(item.elapsed_seconds)}},${{scaleY(item[field])}}`).join(' ');
      svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
      svg.innerHTML = `
        <polyline fill="none" stroke="${{color}}" stroke-width="2" points="${{polyline}}"></polyline>
        <text x="12" y="18" fill="#4b5563">min: ${{minY.toFixed(2)}}</text>
        <text x="${{width - 100}}" y="18" fill="#4b5563">max: ${{maxY.toFixed(2)}}</text>
      `;
    }}

    function createRouteChart() {{
      const svg = document.getElementById("routeChart");
      const points = rows.filter(item => item.latitude !== null && item.longitude !== null);
      if (!points.length) {{
        svg.innerHTML = '<text x="20" y="30" fill="#6b7280">没有 GPS 数据</text>';
        return;
      }}
      const width = svg.clientWidth || 500;
      const height = svg.clientHeight || 220;
      const padding = 20;
      const xs = points.map(item => item.longitude);
      const ys = points.map(item => item.latitude);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const scaleX = value => padding + ((value - minX) / Math.max(maxX - minX, 1e-9)) * (width - padding * 2);
      const scaleY = value => height - padding - ((value - minY) / Math.max(maxY - minY, 1e-9)) * (height - padding * 2);
      const polyline = points.map(item => `${{scaleX(item.longitude)}},${{scaleY(item.latitude)}}`).join(' ');
      const start = points[0];
      const end = points[points.length - 1];
      svg.setAttribute('viewBox', `0 0 ${{width}} ${{height}}`);
      svg.innerHTML = `
        <polyline fill="none" stroke="#2563eb" stroke-width="2" points="${{polyline}}"></polyline>
        <circle cx="${{scaleX(start.longitude)}}" cy="${{scaleY(start.latitude)}}" r="4" fill="#10b981"></circle>
        <circle cx="${{scaleX(end.longitude)}}" cy="${{scaleY(end.latitude)}}" r="4" fill="#ef4444"></circle>
      `;
    }}

    createLineChart("speedChart", "speed_mps", "#2563eb");
    createLineChart("powerChart", "power", "#f97316");
    createLineChart("heartRateChart", "heart_rate", "#ef4444");
    createLineChart("altitudeChart", "altitude_m", "#10b981");
    createRouteChart();
  </script>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_fit)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    reader = FitReader()
    mapper = FitMessageMapper()

    messages = reader.read_file(input_path)
    activity = mapper.map_messages_to_activity(messages)
    summary = mapper.summarize_activity(activity)
    rows = mapper.records_for_visualization(activity)

    base_name = input_path.stem
    summary_path = output_dir / f"{base_name}_summary.json"
    csv_path = output_dir / f"{base_name}_records.csv"
    html_path = output_dir / f"{base_name}_charts.html"

    write_json(summary_path, summary)
    write_csv(csv_path, rows)
    html_path.write_text(build_html(summary, rows), encoding="utf-8")

    print(f"消息数量: {len(messages)}")
    print(f"记录点数量: {len(rows)}")
    print(f"摘要文件: {summary_path}")
    print(f"CSV 文件: {csv_path}")
    print(f"可视化 HTML: {html_path}")


if __name__ == "__main__":
    main()
