# fit_activity_transformer 使用说明

## 1. 项目目标

`fit_activity_transformer` 用于把一个原始 FIT 文件解析成内部活动模型，然后按既定规则完成：

- 停顿处理
- 路线抽象
- 时间轴压缩
- 速度倍率提升
- GPS 与海拔重采样
- 导出新的 FIT 文件

当前版本已经完成从原始 FIT 到新 FIT 的最小闭环。

## 2. 当前可用命令

### 2.1 查看原始 FIT 内容与可视化

```bash
python fit_activity_transformer/inspect_fit.py \
  /home/liuhaowen/codes/garmin_downloader/22321570804_ACTIVITY.fit
```

输出内容：

- 原始摘要 JSON
- 原始 records CSV
- 原始图表 HTML

### 2.2 Step1：停顿检测与 1Hz 归一化

```bash
python fit_activity_transformer/step1_preprocess_demo.py \
  /home/liuhaowen/codes/garmin_downloader/22321570804_ACTIVITY.fit \
  --pause-strategy remove
```

常用参数：

- `--pause-strategy`
  - `remove`
  - `keep`
  - `compress`
- `--compressed-gap-seconds`
  - 仅在 `compress` 时生效

### 2.3 Step2：路线抽象

```bash
python fit_activity_transformer/step2_route_demo.py \
  /home/liuhaowen/codes/garmin_downloader/22321570804_ACTIVITY.fit \
  --pause-strategy compress \
  --compressed-gap-seconds 5
```

输出内容：

- 路线摘要 JSON
- 路线点 CSV
- 距离采样 CSV
- 路线演示 HTML

### 2.4 Step3：停顿策略对比

```bash
python fit_activity_transformer/step3_pause_strategy_demo.py \
  /home/liuhaowen/codes/garmin_downloader/22321570804_ACTIVITY.fit \
  --compressed-gap-seconds 5
```

输出内容：

- 不同停顿策略对比摘要 JSON

### 2.5 Step4：时间轴与速度变换

```bash
python fit_activity_transformer/step4_transform_demo.py \
  /home/liuhaowen/codes/garmin_downloader/22321570804_ACTIVITY.fit \
  --speed-multiplier 1.5 \
  --pause-strategy compress \
  --compressed-gap-seconds 5
```

输出内容：

- 时间轴与距离调度摘要 JSON
- 原始曲线 CSV
- 距离调度 CSV
- 变换演示 HTML

### 2.6 Step5：GPS 与海拔重采样

```bash
python fit_activity_transformer/step5_gps_resample_demo.py \
  /home/liuhaowen/codes/garmin_downloader/22321570804_ACTIVITY.fit \
  --speed-multiplier 1.5 \
  --pause-strategy compress \
  --compressed-gap-seconds 5
```

输出内容：

- 重采样摘要 JSON
- 原始路线 CSV
- 重采样轨迹 CSV
- 重采样演示 HTML

### 2.7 Step6：导出新的 FIT 文件

```bash
python fit_activity_transformer/step6_fit_writer_demo.py \
  /home/liuhaowen/codes/garmin_downloader/22321570804_ACTIVITY.fit \
  --speed-multiplier 1.5 \
  --pause-strategy compress \
  --compressed-gap-seconds 5
```

输出内容：

- 新 FIT 文件
- 导出结果摘要 JSON

## 3. 当前推荐命令

如果你的目标是：

- 从原始 FIT 生成一个新的加速版 FIT
- 保留停顿语义但压缩停顿时长

推荐直接运行：

```bash
python fit_activity_transformer/step6_fit_writer_demo.py \
  /home/liuhaowen/codes/garmin_downloader/22321570804_ACTIVITY.fit \
  --speed-multiplier 1.5 \
  --pause-strategy compress \
  --compressed-gap-seconds 5
```

## 4. 当前示例结果

输入文件：

- `22321570804_ACTIVITY.fit`

当前一组已验证结果如下：

- 停顿策略：`compress`
- 停顿压缩秒数：`5.0`
- 速度倍率：`1.5`
- 原始记录点数量：`1414`
- 重采样点数量：`954`
- 输出 FIT 回读记录点数量：`954`
- 输出 FIT 回读 lap 数量：`1`
- 输出 FIT 回读 session 存在：`true`
- 第一条记录时间：`2026-03-28T00:32:13+00:00`
- 最后一条记录时间：`2026-03-28T00:48:05+00:00`
- 最后距离：`9093.1 m`

## 5. 当前输出文件位置

输出目录：

- `fit_activity_transformer/output/`

当前关键文件包括：

- `22321570804_ACTIVITY_step6_transformed.fit`
- `22321570804_ACTIVITY_step6_fit_writer_summary.json`
- `22321570804_ACTIVITY_step5_gps_demo.html`
- `22321570804_ACTIVITY_step4_transform_demo.html`
- `22321570804_ACTIVITY_step2_route_demo.html`

## 6. 当前接口说明

### 停顿策略接口

- `remove`
  - 将停顿压缩到 1 秒
- `keep`
  - 保留原始停顿
- `compress`
  - 将停顿压缩到指定秒数

### 速度倍率接口

- `--speed-multiplier`
  - 控制时间轴压缩和目标速度放大
  - 例如：
    - `1.2`
    - `1.5`
    - `2.0`

### 输出目录接口

- `--output-dir`
  - 控制所有中间结果和最终 FIT 的输出目录

## 7. 当前限制

- 当前新 FIT 只写回最小可用字段集合
- 目前主要写回：
  - 时间
  - GPS
  - 距离
  - 海拔
  - 速度
  - lap / session / activity 基础汇总
- 当前尚未完整写回：
  - 心率
  - 功率
  - 踏频
  - 更完整的 Garmin 原始扩展字段

## 8. 后续增强方向

- 增加统一 CLI 入口，替代 step 脚本命名
- 增加心率、功率、踏频联动写回
- 增加地图或 DEM 高程替换能力
- 增加导出后与原始文件的对比分析页
