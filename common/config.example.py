# Copy to config.py and fill actual environment and resource IDs.
"""唯一配置入口。服务器地址只改SERVER_HOST；其他参数在TEST_CONFIG中配置。"""
import ipaddress
from pathlib import Path
BASE_DIR = Path(__file__).parent.parent
SERVER_HOST = '127.0.0.1'
TEST_CONFIG = {'host': SERVER_HOST, 'locator_port': 22000, 'protocol': 'tcp', 'service': 'commonService', 'adapter': 'dbProxy-1.dbProxyAdapter', 'version': '1.0', 'topology': 'dual', 'primary_device_id': 'MainDev', 'secondary_device_id': 'meeting2', 'room_id': None, 'user_id': None, 'username': '', 'user_password': '', 'user_update_mode': 'nonempty_fields', 'user_fixture_mode': 'temporary_api', 'user_fixture_api_scheme': 'http', 'user_fixture_api_port': 28080, 'user_fixture_api_account': None, 'device_verify_code': '', 'face_enabled': False, 'face_id': None, 'cdn_enabled': False, 'phone_gateway_enabled': False, 'record_global_switch': None, 'file_parent_id': '', 'test_service_app_id': 54011, 'test_route_app_id': 54012, 'test_master_server_type': 54013, 'scope': 'global', 'excel_path': 'data/test_cases.xlsx', 'report_output': 'allure_report', 'allure_cli': 'tools\\allure-2.18.1\\bin\\allure.bat', 'java_home': 'tools\\jre8', 'database': {'backend': 'auto', 'host': SERVER_HOST, 'ssh_port': 22, 'user': 'root', 'password': '', 'config_dir': None}}

def _path(value: str) -> Path:
    """相对路径按包根目录解析；绝对路径原样返回。"""
    p = Path(value)
    return p if p.is_absolute() else BASE_DIR / p

def build_ice_locator(host, port=22000, protocol='tcp'):
    host = str(host).strip().strip('\'"')
    try:
        ipaddress.ip_address(host.split('%', 1)[0])
        if ':' in host:
            host = f'"{host}"'
    except ValueError:
        pass
    return f'IceGrid/Locator:{protocol} -h {host} -p {port}'
ICE_CONFIG = {'locator': build_ice_locator(TEST_CONFIG['host'], TEST_CONFIG['locator_port'], TEST_CONFIG['protocol']), 'service': TEST_CONFIG['service'], 'adapter': TEST_CONFIG['adapter']}
EXCEL_CONFIG = {'file_path': str(_path(TEST_CONFIG['excel_path'])), 'sheet_name': 'TestCases'}
ALLURE_CONFIG = {'report_dir': str(BASE_DIR / 'allure-results'), 'history_dir': str(BASE_DIR / 'allure-report/history'), 'output_dir': str(_path(TEST_CONFIG['report_output'])), 'cli': str(_path(TEST_CONFIG['allure_cli'])), 'java_home': str(_path(TEST_CONFIG['java_home']))}
LOG_CONFIG = {'level': 'DEBUG', 'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'}
