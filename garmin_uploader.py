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
        email = self.config.get('garmin_username_global') 
        password = self.config.get('garmin_password_global')
        
        if not email or not password:
            raise Exception("config.yaml中需要配置garmin_username和garmin_password")
        
        print("使用用户名密码登录国际区Garmin...")
        self.client = Garmin(email, password, is_cn=False)
        
        try:
            self.client.login()
            print("登录成功！")
        except Exception as e:
            error_msg = str(e)
            if "Update Phone Number" in error_msg:
                print("\n登录失败：Garmin要求验证手机号码")
                print("这是Garmin的安全要求，无法通过用户名密码直接登录。")
                print("\n解决方案：")
                print("1. 登录Garmin网站，完成手机号码验证")
                print("2. 或者使用session文件方式登录（需要先在浏览器登录后获取session）")
                print("3. 查看garminconnect文档了解如何使用token方式登录")
                raise Exception("Garmin要求验证手机号码，请先在Garmin网站完成验证")
            raise
    
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
                # 检查文件是否存在和大小
                if not os.path.exists(fit_file):
                    print(f"  文件不存在: {fit_file}")
                    continue
                    
                file_size = os.path.getsize(fit_file)
                print(f"  文件大小: {file_size} bytes")
                
                if file_size == 0:
                    print(f"  文件为空，跳过")
                    continue
                
                result = self.client.import_activity(fit_file)
                print(f"  上传成功！")
                    
            except Exception as e:
                print(f"  上传失败: {str(e)}")
                import traceback
                traceback.print_exc()
    
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