import yaml
import json
import os
from garminconnect import Garmin

os.environ['GARMIN_DOMAIN'] = 'garmin.cn'

class GarminDownloader:
    def __init__(self, config_file='config.yaml'):
        self.config_file = config_file
        self.config = self._load_config()
        self.client = None
        
    def _load_config(self):
        with open(self.config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def login(self):
        email = self.config.get('garmin_username')
        password = self.config.get('garmin_password')
        
        if not email or not password:
            raise Exception("config.yaml中需要配置garmin_username和garmin_password")
        
        print("使用用户名密码登录中国区Garmin...")
        self.client = Garmin(email, password, is_cn=True)
        
        self.client.login()
        print("登录成功！")
    
    def download_fit_files(self):
        if not self.client:
            raise Exception("请先登录")
        
        download_count = self.config.get('download_count', 5)
        activities = self.client.get_activities(0, download_count)
        
        if not activities:
            print("没有找到活动记录")
            return
        
        output_dir = 'fit_files'
        os.makedirs(output_dir, exist_ok=True)
        
        for activity in activities:
            activity_id = activity['activityId']
            activity_name = activity.get('activityName', f'activity_{activity_id}')
            start_time = activity.get('startTimeLocal', 'unknown')
            
            print(f"下载活动: {activity_name} (ID: {activity_id})")
            
            try:
                fit_data = self.client.download_activity(
                    activity_id, 
                    Garmin.ActivityDownloadFormat.ORIGINAL
                )
                
                if fit_data:
                    filename = f"{output_dir}/{activity_name.replace('/', '_')}_{activity_id}.fit"
                    with open(filename, 'wb') as f:
                        f.write(fit_data)
                    print(f"  FIT文件已保存到: {filename}")
                else:
                    print(f"  无法下载FIT文件")
                    
            except Exception as e:
                print(f"  下载FIT文件失败: {str(e)}")
    
    def run(self):
        try:
            self.login()
            self.download_fit_files()
            print("\n下载完成！")
        except Exception as e:
            print(f"错误: {str(e)}")
            if "Update Phone Number" in str(e) or "Unexpected title" in str(e):
                print("\n解决方案：")
                print("1. 在浏览器中登录 https://connect.garmin.cn")
                print("2. 完成手机号码验证后再运行此程序")
                print("3. 或者使用MFA验证，在配置文件中添加mfa_code字段")

if __name__ == '__main__':
    downloader = GarminDownloader()
    downloader.run()