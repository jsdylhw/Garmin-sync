import os
import glob
from garminconnect import Garmin

os.environ['GARMIN_DOMAIN'] = 'garmin.com'

class GarminUploader:
    def __init__(self, config_file='config.yaml'):
        self.config_file = config_file
        self.config = self._load_config()
        self.client = None
        
    def _load_config(self):
        import yaml
        with open(self.config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def login(self):
        email = self.config.get('garmin_username')
        password = self.config.get('garmin_password')
        
        if not email or not password:
            raise Exception("config.yaml中需要配置garmin_username和garmin_password")
        
        print("使用用户名密码登录国际区Garmin...")
        self.client = Garmin(email, password, is_cn=False)
        
        self.client.login()
        print("登录成功！")
    
    def upload_fit_files(self, fit_dir='fit_files'):
        if not self.client:
            raise Exception("请先登录")
        
        fit_files = glob.glob(f"{fit_dir}/*.fit")
        
        if not fit_files:
            print(f"在 {fit_dir} 目录中没有找到FIT文件")
            return
        
        print(f"找到 {len(fit_files)} 个FIT文件")
        
        for fit_file in fit_files:
            filename = os.path.basename(fit_file)
            print(f"上传文件: {filename}")
            
            try:
                with open(fit_file, 'rb') as f:
                    result = self.client.upload_activity(f)
                    print(f"  上传成功！")
                    
            except Exception as e:
                print(f"  上传失败: {str(e)}")
    
    def run(self):
        try:
            self.login()
            self.upload_fit_files()
            print("\n上传完成！")
        except Exception as e:
            print(f"错误: {str(e)}")

if __name__ == '__main__':
    uploader = GarminUploader()
    uploader.run()