# Garmin 运动记录下载器

从Garmin账号下载最近的运动记录（FIT文件），用于中国区和国际区数据同步。

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置

编辑 `config.yaml` 文件：

```yaml
garmin_username: your_username
garmin_password: your_password
download_count: 5
```

- `garmin_username`: Garmin用户名（邮箱）
- `garmin_password`: Garmin密码
- `download_count`: 要下载的最近活动数量（默认5次）

**重要**: `config.yaml` 已添加到 `.gitignore`，不会提交到版本控制。

## 使用方法

```bash
python garmin_downloader.py
```

下载的FIT文件会保存在 `fit_files/` 目录下，每个活动一个.fit文件。

## 数据同步

### 中国区 → 国际区
1. 使用中国区账号配置运行程序下载FIT文件
2. 将FIT文件上传到国际区Garmin账号

### 国际区 → 中国区
1. 修改代码中的 `is_cn=False` 使用国际区账号
2. 下载FIT文件后上传到中国区账号

## 注意事项

- 请确保不要将 `config.yaml` 提交到公开仓库
- 首次运行可能需要在浏览器中完成手机验证
- 下载的数据包含个人运动信息，请妥善保管