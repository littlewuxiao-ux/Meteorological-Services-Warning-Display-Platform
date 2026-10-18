import base64
import json
import time

import requests
from PIL import Image
from io import BytesIO

from utils.cas_api_log import log_cas_api_request

session = requests.session()


def reset_cas_http_session():
    """新开一次扫码前清空服务端 CAS HTTP 会话，避免沿用上次已扫码状态。"""
    global session
    try:
        session.close()
    except Exception:
        pass
    session = requests.session()

get_qar_url = "https://cas.sf-express.com/cas/qrcode?type=cXJjb2Rl"
listion_scan_qrcode_url = "https://cas.sf-express.com/cas/qrcode?type=dmFsaWRhdGlvbg"
validate_url = "https://sfa-gwgw-inn.sf-airlines.com:8443/apis-auth/login/cas3.0"


def get_config():
    """
    根据serviceId获得配置信息
    :return:
    """
    data = {
        "serviceId": "sfa-gwgw-inn.sf-airlines.com"
    }
    url = "https://cas.sf-express.com/cas/app/getConfig"
    log_cas_api_request(url, user_id='(未登录)', has_token=False)
    response = session.post(url=url, json=data)
    json_str = json.loads(response.text)
    return json_str


def get_qrcode(config):
    """
    获取二维码信息
    """
    reset_cas_http_session()
    headers = {
        "routing": config.get("routing")
    }
    log_cas_api_request(get_qar_url, user_id='(未登录)', has_token=False)
    response = session.get(get_qar_url, headers=headers)
    json_str = json.loads(response.text).get("data")
    return {
        "qr_id": json_str.get("id"),
        "qr_img_base64": json_str.get("img"),
        "routing": config.get("routing")
    }

def check_scan_status(qr_id, routing):
    """
    检查扫码状态
    """
    params = {
        "routing": routing,
        "id": qr_id,
        "responseHeaders": "true"
    }
    log_cas_api_request(listion_scan_qrcode_url, user_id='(扫码中)', has_token=False)
    response = session.get(listion_scan_qrcode_url, params=params)
    response_data = json.loads(response.text)
    if response_data.get("success") == True:
        scan_data = response_data.get("data")
        return {
            "success": True,
            "userCode": scan_data.get("userCode"),
            "ticket": scan_data.get("ticket"),
            "id": scan_data.get("id")
        }
    else:
        return {"success": False}

def qrcode_login(config):
    headers = {
        "routing": config.get("routing")
    }
    log_cas_api_request(get_qar_url, user_id='(未登录)', has_token=False)
    response = session.get(get_qar_url, headers=headers)
    json_str = json.loads(response.text).get("data")
    img_data = base64.b64decode(json_str.get("img"))
    byte_stream = BytesIO(img_data)
    img = Image.open(byte_stream)
    img.show()
    listen_times = 0
    while True:
        time.sleep(2)
        params = {
            "routing": config.get("routing"),
            "id": json_str.get("id"),
            "responseHeaders": "true"
        }
        response2 = session.get(listion_scan_qrcode_url, params=params)
        json_str2 = json.loads(response2.text).get("data")
        if json.loads(response2.text).get("success") == True:
            print("扫码成功:" + json_str2.get("userCode"))
            return json_str2
        else:
            print("第" + str(listen_times + 1) + "次请求扫码结果失败")


def validate_login(config, scan_qrcode_result):
    headers = {
        "routing": config.get("routing")
    }
    decode_once = base64.b64decode(scan_qrcode_result.get("id")).decode("ascii")
    decode_twice = base64.b64decode(decode_once).decode("ascii")
    data = {
        "st": scan_qrcode_result.get("ticket"),
        "service": decode_twice,
        "appKey": "mtws_foc2",
        "appSecret": "mtwsFoc2#123"
    }
    user_id = scan_qrcode_result.get("userCode") or '(扫码成功待换票)'
    log_cas_api_request(validate_url, user_id=user_id, has_token=False)
    response = session.post(validate_url, headers=headers, json=data)
    json_str = json.loads(response.text)
    print("登录成功")
    return json_str.get("obj").get("token")


def logout(token):
    """
    登出
    
    Args:
        token: 登录时获取的token
        
    Returns:
        bool: 登出是否成功
    """
    try:
        logout_url = "http://sfa-wgw-inn.sf-airlines.com:1080/apis-auth/login/logout"
        log_cas_api_request(logout_url, has_token=bool(token))
        headers = {
            'token': token,
            'Content-Type': 'application/json'
        }
        response = session.post(logout_url, headers=headers)
        if response.status_code == 200:
            print("登出成功")
            return True
        else:
            print(f"登出失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"登出异常: {e}")
        return False

def login():
    print("正在登录cas")
    config = get_config()
    scan_qrcode_result = qrcode_login(config)
    token = validate_login(config, scan_qrcode_result)
    return token

if __name__ == '__main__':
    token = login()
    print(token)