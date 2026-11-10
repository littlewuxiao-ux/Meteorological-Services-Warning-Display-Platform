# FMSA 一键登录改造 · 移植说明书

> **这份文档是给 AI 读的。** 读完它 + 一份「改动前」的 FMSA 工程，即可把工程改造成「现在」的版本。
>
> - 生成日期：2026-11-09
> - 适用工程：Django 工程目录名为 `fmsa_django` 的那一支（工程根目录同时有 `启动FMSA系统.bat`、`fmsa_django/manage.py`）
> - 不适用：工程目录名为 `mtws_django` 的那一支 —— 见文末「附录 A」

---

## 0. 这次改造做了什么

两件事，第二件是第一件的延续：

1. **登录页改版**：把居中的小弹框改成**全屏 CAS 风格登录页**（品牌区 + 登录卡片 + 底部提示条）。只换皮，不动登录逻辑。
2. **新增「一键登录」**：底部提示条上的「立即登录」按钮接活。用户点一下，**在自己的浏览器里**向 sflinksso 取 sflink 票据，把票据 POST 给后端；后端拿票据走 CAS 换 ST、再换业务 token，返回与扫码登录**同形**的 `{token, userCode}`。

扫码登录**原样保留**，是一键登录不可用时的兜底。

### 0.1 链路

```
浏览器（用户机器）                        FMSA 服务端
   │                                          │
   │ ① GET sflinksso auth_login               │   源 IP = 用户机器 → sub = 用户工号
   │    ← sflink 票据（JWT，180s）             │
   │                                          │
   │ ② POST /current/api/auth/one-click-login/│
   │    {ticket}                              │
   │                                          │ ③ GET  CAS /login?service=… → lt + cookie
   │                                          │ ④ POST CAS 同一地址 verifyType=sflinkTicket
   │                                          │      + dynamicPassword=<ticket> → 302 ?ticket=ST-…
   │                                          │ ⑤ POST 网关 cas3.0 {st, service, appKey, appSecret}
   │    ← {token, userCode}                   │      → obj.token
```

### 0.2 ★ 一条不可动摇的设计约束

**第 ① 步取票据必须在浏览器里做，不能挪到服务端。**

依据：sflinksso 的 `auth_login` 接口只带 `app_id` / `time_stamp` / `sole_id` 三个参数，**没有任何设备标识**，身份完全由**请求的来源 IP** 决定。

- 浏览器取 → 拿到「用户本机」的丰声身份（桌面版=本人，Web 版=访问者本人）✅
- 服务端取 → 拿到「服务器」的身份，Web 部署下会把**所有用户登成同一人** ❌

> **给 AI 的硬性要求**：改造完成后，`sflink_login.py` 里**不应存在**任何向 sflinksso 取票据的代码；票据只能从视图的请求体里来。如果看到有人（包括你自己）试图把它「优化」成服务端取票据，那是**退化**，必须拒绝。

---

## 1. 执行前的前置检查

**任一项不满足，就停下来报告，不要继续。**

| 检查项 | 期望 | 不满足时 |
|---|---|---|
| 工程目录 | 存在 `fmsa_django/manage.py` | 目标不是这一支，**停止**（见附录 A） |
| `fmsa_django/utils/sf_env.py` | 存在，导出 `env` / `require` / `intranet_url` | 从新版一并复制该文件 |
| `fmsa_django/utils/cas_api_log.py` | 存在，导出 `log_cas_api_request` / `cas_user_context` | 从新版一并复制该文件 |
| `fmsa_django/api/views.py` | 含 `def check_login_status(` | 结构不符，**停止** |
| `fmsa_django/api/cas_login.py` | 含 `def validate_login(` | 结构不符，**停止** |

### 1.1 编码要求（很重要，不遵守会导致锚点匹配失败）

改动每个文件时：

1. 先探测该文件**是否带 UTF-8 BOM**（开头三字节 `\xef\xbb\xbf`）与**行尾是 CRLF 还是 LF**。
2. 匹配锚点**之前**，把 `\r\n` 统一替换成 `\n`；否则带 CRLF 的文件会一条都匹配不上。
3. 写回时**还原**原来的 BOM 与行尾风格，不要顺手统一。

---

## 2. 改动总览

工程根目录记为 `<FMSA>`。

| # | 文件（相对 `<FMSA>`） | 动作 | 目标大小 | 目标 SHA256（前 16 位） |
|---|---|---|---|---|
| 1 | `fmsa_django/api/sflink_login.py` | **新增** | 7,657 B | `587446F295B824EA` |
| 2 | `fmsa_django/api/cas_login.py` | 改 2 处 | 5,414 B | `E12DB7C99FE1476B` |
| 3 | `fmsa_django/api/urls.py` | 加 1 行 | 8,636 B | `D8AF2F4732E14DC1` |
| 4 | `fmsa_django/api/views.py` | 加 1 个视图 | 85,755 B | `55ECCF4A39A24E40` |
| 5 | `fmsa_django/web/views.py` | 改 2 处 | 4,208 B | `FCE6D7534ADA8F9B` |
| 6 | `fmsa_django/static/js/main.js` | 加 4 函数 + 改 1 处 | 184,531 B | `BD0C6FF145EA69CA` |
| 7 | `fmsa_django/static/css/main.css` | 替换 1 个样式块 | 149,426 B | `E1AE3585FC1E0D53` |
| 8 | `fmsa_django/templates/web/index.html` | 改 2 处 | 60,615 B | `5387F37C778EFC22` |
| 9 | `<FMSA>/.env` | **追加** 6 个键 | 1,049 B | `7D0E7361D5A7207F` |

**不改动**：任何 `models.py`、任何迁移文件、`access_control.py`、`auth_broker_client.py`、数据库结构。

> 文件 6 / 7 / 8 同时承载了「登录页改版」和「一键登录」两件事——新版文件里两者已合并，一次覆盖即到位。

---

## 3. 逐文件改动

改动点全部用「**改动前**（锚点，必须逐字匹配）→ **现在**（替换成）」给出。

### 3.1 新增 `fmsa_django/api/sflink_login.py`

新建该文件，内容**逐字**如下（7,657 字节）：

```python
# -*- coding: utf-8 -*-
"""一键登录：sflink 票据 -> CAS 票据(ST) -> FMSA token。

★ 票据由**浏览器**取，不由服务端取 —— 这是本模块最关键的设计约束。

sflinksso 的 auth_login 接口只带 app_id / time_stamp / sole_id 三个参数，
没有任何设备标识，身份完全由请求的来源决定。因此：

  * 浏览器取票据 -> 拿到「用户本机」的丰声身份（桌面版=本人，Web 版=访问者本人）
  * 服务端取票据 -> 拿到「服务器」的身份，Web 部署下会把所有人都登成同一人

所以第 1 步必须在浏览器里做。本模块只负责第 2-4 步：拿浏览器递上来的票据
去 CAS 换 ST，再拿 ST 去网关换业务 token。这三步是纯协议转换，与「谁发起的」
无关，放服务端还能让 appKey/appSecret 不下发前端。

链路（2026-11-09 实测打通）：
  1. （浏览器）GET {SF_SFLINK_BASE_URL}/api/public/clientlogin/auth_login -> JWT 票据
  2. GET  {SF_CAS_BASE_URL}/login?service={SF_CAS_SERVICE_URL}   -> lt + cookie
  3. POST 同一地址，verifyType=sflinkTicket                       -> 302 ?ticket=ST-...
  4. POST {SF_CAS_VALIDATE_URL}                                   -> obj.token

三个容易踩的点：

  * service 必须是 SF_CAS_SERVICE_URL（带 scheme 和端口）。传裸主机名会命中
    CAS 的「安全级别更高，需二次校验」分支，第 3 步拿不到 ST。
    它与 SF_CAS_SERVICE_ID 语义不同：后者是裸主机名，只给 getConfig 当
    serviceId 用，两者不可互换。

  * 密码字段在 sflinkTicket 路径下不参与校验。实测：固定串、真实密码、
    故意写错的密码都能通过，只有空值会被表单卡住。因此本模块不保存任何
    密码，直接沿用 CAS 自身 loginFsnext() 里的那个固定串。

  * 四步必须连着走完。ST 一次性且只有 180 秒寿命，中途失败无法续跑。
"""

import base64
import json
import re
from urllib.parse import unquote

import requests

from utils.cas_api_log import log_cas_api_request
from utils.sf_env import require

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

_TIMEOUT = 10

# 密码不参与校验，照抄 CAS 自身 loginFsnext() 的固定串即可，无需进 .env。
_CAS_FORM_PASSWORD = 'active123.'

_LT_RE = re.compile(r'name="lt"\s+value="([^"]+)"')
_HIDDEN_RE = re.compile(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"')
_ST_RE = re.compile(r'ticket=(ST-[^&]+)')


class SflinkLoginError(Exception):
    """一键登录失败。message 面向用户，可直接提示。"""


def _decode_user_code(ticket):
    """从 JWT payload 里取 sub（工号）。"""
    try:
        payload = ticket.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload).decode('utf-8'))
    except Exception as exc:
        raise SflinkLoginError('无法解析 sflink 票据') from exc
    user_code = str(data.get('sub') or '').strip()
    if not user_code:
        raise SflinkLoginError('sflink 票据里没有工号')
    return user_code


def get_cas_lt(session, service):
    """第 2 步：打开 CAS 登录页取 lt。返回 (login_url, lt, hidden_fields)。"""
    login_url = require('SF_CAS_BASE_URL').rstrip('/') + '/login'
    try:
        response = session.get(login_url, params={'service': service},
                               headers={'User-Agent': _UA}, timeout=_TIMEOUT)
    except Exception as exc:
        raise SflinkLoginError('无法打开 CAS 登录页') from exc

    html = response.text or ''
    matched = _LT_RE.search(html)
    if not matched:
        raise SflinkLoginError('CAS 登录页未返回 lt（service 可能不被识别）')
    return login_url, matched.group(1), dict(_HIDDEN_RE.findall(html))


def submit_cas_login(session, login_url, lt, hidden_fields, user_code, ticket):
    """第 3 步：提交登录表单，从 302 的 Location 里取 ST。"""
    form = dict(hidden_fields)
    form.update({
        'username': user_code,
        'password': _CAS_FORM_PASSWORD,
        'lt': lt,
        'verifyType': 'sflinkTicket',
        'dynamicPassword': ticket,
        '_eventId': 'submit',
        'qrcodeId': '',
    })
    try:
        response = session.post(login_url, data=form,
                                headers={'User-Agent': _UA, 'Referer': login_url},
                                allow_redirects=False, timeout=_TIMEOUT)
    except Exception as exc:
        raise SflinkLoginError('提交 CAS 登录失败') from exc

    location = response.headers.get('Location') or ''
    matched = _ST_RE.search(location)
    if not matched:
        raise SflinkLoginError('CAS 未返回票据（ST）')
    return unquote(matched.group(1))


def _fetch_routing():
    """取 getConfig 的 routing，作为换票请求头。

    刻意不复用 cas_login.get_config()：那个函数走的是扫码流程的全局 session，
    会把 CAS 的 Set-Cookie 种进扫码会话。这里用一次性请求，互不干扰。
    拿不到时返回 None —— 实测不带 routing 也能换到 token。
    """
    try:
        response = requests.post(
            require('SF_CAS_CONFIG_URL'),
            json={'serviceId': require('SF_CAS_SERVICE_ID')},
            headers={'User-Agent': _UA},
            timeout=_TIMEOUT,
        )
        return (response.json() or {}).get('routing')
    except Exception:
        return None


def exchange_token(st, service, user_code):
    """第 4 步：拿 ST 到网关换 FMSA token。

    与扫码路径走同一个网关地址、同一对密钥（都从 .env 取），
    所以换回来的 token 形状与扫码完全一致。
    """
    from .cas_login import gateway_credentials

    headers = {'User-Agent': _UA}
    routing = _fetch_routing()
    if routing:
        headers['routing'] = routing

    app_key, app_secret = gateway_credentials()
    payload = {'st': st, 'service': service, 'appKey': app_key, 'appSecret': app_secret}

    validate_url = require('SF_CAS_VALIDATE_URL')
    log_cas_api_request(validate_url, user_id=user_code, has_token=False)
    try:
        response = requests.post(validate_url, headers=headers, json=payload,
                                 timeout=_TIMEOUT)
        body = response.json()
    except Exception as exc:
        raise SflinkLoginError('换取登录凭证失败') from exc

    token = str(((body or {}).get('obj') or {}).get('token') or '').strip()
    if not token:
        raise SflinkLoginError(str((body or {}).get('errorMessage') or '换取登录凭证失败'))
    return token


def one_click_login(ticket):
    """拿浏览器递上来的 sflink 票据换 FMSA token。

    ticket 由前端调用 sflinksso 取得，必须是用户本机发起的请求 ——
    本模块不再自己取票据，否则 Web 部署下会拿到服务器的身份。

    成功返回 (token, user_code)，失败抛 SflinkLoginError。
    """
    ticket = str(ticket or '').strip()
    if not ticket:
        raise SflinkLoginError('缺少 sflink 票据')

    service = require('SF_CAS_SERVICE_URL')
    user_code = _decode_user_code(ticket)

    session = requests.session()
    try:
        login_url, lt, hidden_fields = get_cas_lt(session, service)
        st = submit_cas_login(session, login_url, lt, hidden_fields, user_code, ticket)
        token = exchange_token(st, service, user_code)
        return token, user_code
    finally:
        try:
            session.close()
        except Exception:
            pass
```

**两个必须保留的实现细节**（改「优化」掉会出问题）：

- 本模块用**自己的** `requests.session()`，**绝不能**复用 `cas_login.session`。后者被 `reset_cas_http_session()` 在每次扫码前清空，共用会让扫码和一键登录互相踩 cookie。
- `_fetch_routing()` **刻意不调** `cas_login.get_config()`（那会往扫码会话里种 Set-Cookie），改用一次性请求。

---
### 3.2 `fmsa_django/api/cas_login.py` —— 改 2 处

**目的**：把原本写死在代码里的网关密钥改为从 `.env` 读。**纯取值替换**，`validate_login` 的入参、出参、调用时序、请求体结构全部不变，扫码路径行为零变化。

#### 3.2.1 在 `reset_cas_http_session()` 之后插入新函数

**改动前**：

```python
    except Exception:
        pass
    session = requests.session()

def get_config():
```

**现在**：

```python
    except Exception:
        pass
    session = requests.session()

def gateway_credentials():
    """网关换票所需的 appKey / appSecret（从 .env 读取）。

    扫码路径与一键登录路径共用这一份，代码里不再保留明文拷贝。
    """
    return require('SF_CAS_APP_KEY'), require('SF_CAS_APP_SECRET')


def get_config():
```

> 注意：原文件里 `session = requests.session()` 与 `def get_config():` 之间**只有一个空行**。新版这里是两个空行。

#### 3.2.2 `validate_login()` 里改用变量

**改动前**（在 `validate_login` 函数体内）：

```python
    decode_once = base64.b64decode(scan_qrcode_result.get("id")).decode("ascii")
    decode_twice = base64.b64decode(decode_once).decode("ascii")
    data = {
        "st": scan_qrcode_result.get("ticket"),
        "service": decode_twice,
        "appKey": "<原文件中写死的 appKey 字面量>",
        "appSecret": "<原文件中写死的 appSecret 字面量>"
    }
```

**现在**：

```python
    decode_once = base64.b64decode(scan_qrcode_result.get("id")).decode("ascii")
    decode_twice = base64.b64decode(decode_once).decode("ascii")
    app_key, app_secret = gateway_credentials()
    data = {
        "st": scan_qrcode_result.get("ticket"),
        "service": decode_twice,
        "appKey": app_key,
        "appSecret": app_secret
    }
```

> 把两处 `<...字面量>` 换成原文件里实际写着的值即可 —— **这两个值随后要原样搬进 `.env`**（见 3.9）。定位方法：在原 `cas_login.py` 里搜 `"appKey"`。

**前置条件**：该文件顶部必须已有 `from utils.sf_env import intranet_url, require`。若没有，先补上（`require` 是 `gateway_credentials` 用到的）。

---

### 3.3 `fmsa_django/api/urls.py` —— 加 1 行

**改动前**：

```python
    # 鉴权相关API（仅用于current模式）
    path('auth/get-qrcode/', views.get_qrcode, name='get_qrcode'),
    path('auth/check-login/', views.check_login_status, name='check_login_status'),
    path('auth/logout/', views.logout, name='logout'),
```

**现在**：

```python
    # 鉴权相关API（仅用于current模式）
    path('auth/get-qrcode/', views.get_qrcode, name='get_qrcode'),
    path('auth/check-login/', views.check_login_status, name='check_login_status'),
    path('auth/one-click-login/', views.one_click_login, name='one_click_login'),
    path('auth/logout/', views.logout, name='logout'),
```

---

### 3.4 `fmsa_django/api/views.py` —— 新增 1 个视图

**插入位置**：紧跟在 `check_login_status` 视图结束之后、`seat_identity` 视图之前。

**改动前**（定位用，这一段保持不变）：

```python
        }, status=500)


@require_http_methods(["GET"])
def seat_identity(request, time_mode='current'):
    return JsonResponse({'success': True, 'data': get_seat_identity(request)})
```

**现在**（在两者之间插入）：

```python
        }, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def one_click_login(request, time_mode='current'):
    """
    一键登录API（仅用于current模式）

    sflink 票据由前端在**自己的浏览器**里取（该接口不带任何设备标识，
    身份取决于请求源 IP），这里只负责后续换票。因此不限制调用来源——
    每个调用者带的都是自己的票据，换回的都是自己的 token。

    反过来，如果让服务端去取票据，Web 部署下所有用户都会拿到服务器的身份。
    """
    if time_mode != 'current':
        return JsonResponse({
            'success': False,
            'error': '此接口仅用于current模式'
        }, status=400)

    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except (ValueError, UnicodeDecodeError):
        payload = {}
    ticket = str((payload or {}).get('ticket') or '').strip()
    if not ticket:
        return JsonResponse({
            'success': False,
            'error': '缺少 sflink 票据'
        }, status=400)

    try:
        from .sflink_login import one_click_login as do_one_click_login, SflinkLoginError

        try:
            token, user_code = do_one_click_login(ticket)
        except SflinkLoginError as e:
            logger.warning("一键登录失败: %s" % str(e))
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

        return JsonResponse({
            'success': True,
            'data': {
                'token': token,
                'userCode': user_code
            }
        })

    except Exception as e:
        logger.error("一键登录异常: %s" % str(e))
        return JsonResponse({
            'success': False,
            'error': '一键登录失败',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def seat_identity(request, time_mode='current'):
    return JsonResponse({'success': True, 'data': get_seat_identity(request)})
```

**依赖检查**：该文件顶部需已有 `json`、`logger`、`JsonResponse`、`require_http_methods`、`csrf_exempt`。旧版都有，不用补。

> **不要**在这里加「仅允许回环地址调用」之类的来源限制。那是建立在「服务端取票据」的错误前提上的；现在每个调用者带的是自己的票据，远程访问是正常用法。

---

### 3.5 `fmsa_django/web/views.py` —— 改 2 处

**目的**：把 sflink 的两个配置项下发到页面（它们是**前端要用的配置**，不是服务端凭据）。

#### 3.5.1 补 import

**改动前**：

```python
from utils.flight_selection import selected_carrier_codes, sort_carrier_codes
from utils.time_manager import TimeManager
from django.conf import settings as django_settings
```

**现在**：

```python
from utils.flight_selection import selected_carrier_codes, sort_carrier_codes
from utils.time_manager import TimeManager
from django.conf import settings as django_settings
from utils.sf_env import env
```

#### 3.5.2 `index` 视图的 context 增加两项

**改动前**：

```python
        'chart_default_hours': chart_default_hours,  # 传递图表默认小时数给前端
    }
```

**现在**：

```python
        'chart_default_hours': chart_default_hours,  # 传递图表默认小时数给前端
        # 一键登录：票据由前端在自己的浏览器里取，故这两个值必须下发到页面
        'sflink_base_url': env('SF_SFLINK_BASE_URL'),
        'sflink_app_id': env('SF_SFLINK_APP_ID'),
    }
```

---
### 3.6 `fmsa_django/static/js/main.js` —— 加 4 个函数 + 改 1 处

> **如实说明**：新版里 `handleLoginSuccess()` 是**新加的函数，目前只被一键登录调用**；扫码路径（`check-login` 轮询的成功分支）**仍保留原来的内联代码，未做抽取**。两者逻辑等价但代码重复——这是当前的真实状态，本说明不做「顺手重构」。

#### 3.6.1 插入 4 个新函数

**插入位置**：在某个以 `.forEach((key) => localStorage.removeItem(key));` 结尾的函数之后、`async function initCurrentModeAuth() {` 之前。

**改动前**（定位用）：

```javascript
        .forEach((key) => localStorage.removeItem(key));
}

async function initCurrentModeAuth() {
```

**现在**：

```javascript
        .forEach((key) => localStorage.removeItem(key));
}

// 登录成功后的统一落地流程：扫码与一键登录共用
function handleLoginSuccess(token, userCode) {
    currentToken = token;
    currentUserCode = userCode;
    if (typeof loadAirportDetailTheme === 'function') loadAirportDetailTheme();

    writeStoredAuth(currentToken, currentUserCode);
    updateUnifiedAuth(currentToken, currentUserCode);

    hideLoginModal();
    showUserInfo();

    // 重置token失效标志并重新启动自动刷新
    window.tokenInvalidDetected = false;
    startUnifiedAuthWatch();
    if (!window.autoRefreshTimer) {
        startAutoRefresh();
    }

    // 启动弹窗轮询
    startPopupCheck();

    loadInitialData();
}

// 停掉扫码轮询
function stopQRCodePolling() {
    if (loginCheckInterval) {
        clearInterval(loginCheckInterval);
        loginCheckInterval = null;
    }
    if (qrCodeTimer) {
        clearTimeout(qrCodeTimer);
        qrCodeTimer = null;
    }
}

// 向 sflinksso 取本机 sflink 票据。
// ★ 必须在浏览器里发：该接口不带任何设备标识，身份由请求来源决定。
//   若改由服务端去取，Web 部署下所有用户都会拿到服务器的身份。
function fetchSflinkTicket() {
    const baseUrl = (window.sflinkBaseUrl || '').replace(/\/+$/, '');
    const appId = window.sflinkAppId || '';
    if (!baseUrl || !appId) {
        return Promise.reject(new Error('未配置 sflink 地址'));
    }
    const soleId = Math.random().toString(36).slice(2, 7)
        + Date.now()
        + Math.random().toString(36).slice(2, 5);
    const url = `${baseUrl}/api/public/clientlogin/auth_login`
        + `?app_id=${encodeURIComponent(appId)}`
        + `&time_stamp=${Date.now()}`
        + `&sole_id=${encodeURIComponent(soleId)}`;

    return fetch(url, { method: 'GET' })
        .then(response => response.json())
        .then(data => {
            const code = String(data.errorcode != null ? data.errorcode : data.error_code);
            if (code === '0' && data.ticket) {
                return data.ticket;
            }
            throw new Error('未获取到 sflink 票据');
        });
}

// 一键登录：浏览器取票据 -> 后端换 token（仅 current 模式）
function doOneClickLogin() {
    const btn = document.getElementById('login-oneclick-btn');
    if (!btn || btn.disabled) return;

    const originalText = btn.textContent;
    const setStatus = function (msg) {
        const status = document.getElementById('login-status');
        if (status) status.textContent = msg;
    };
    const restore = function () {
        btn.disabled = false;
        btn.textContent = originalText;
    };

    btn.disabled = true;
    btn.textContent = '登录中...';

    fetchSflinkTicket()
        .then(ticket => fetch(`/${currentTimeMode}/api/auth/one-click-login/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ ticket: ticket })
        }))
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                stopQRCodePolling();
                handleLoginSuccess(data.data.token, data.data.userCode);
            } else {
                // 失败不切页：扫码入口始终可用，作为兜底
                restore();
                setStatus('一键登录失败：' + (data.error || '未知错误') + '，请使用扫码登录');
            }
        })
        .catch(error => {
            console.error('一键登录失败:', error);
            restore();
            setStatus('一键登录失败，请使用扫码登录');
        });
}
window.doOneClickLogin = doOneClickLogin;

async function initCurrentModeAuth() {
```

#### 3.6.2 加 `switchLoginTab()`，并改 `showLoginModal()`

**改动前**：

```javascript
// 显示登录模态框
function showLoginModal() {
    const loginModal = document.getElementById('login-modal');
    if (!loginModal) return;
    ensureLoginModalOnTop();
    loginModal.style.display = 'block';
    getQRCode();
}
```

**现在**：

```javascript
// 显示登录模态框
// 登录页标签切换（扫码 / 一键 / 账密）
function switchLoginTab(tab) {
    const modal = document.getElementById('login-modal');
    if (!modal) return;
    modal.querySelectorAll('.login-tab').forEach(function (el) {
        el.classList.toggle('active', el.dataset.tab === tab);
    });
    modal.querySelectorAll('.login-panel').forEach(function (el) {
        el.classList.toggle('active', el.dataset.panel === tab);
    });
}
window.switchLoginTab = switchLoginTab;

// 显示登录模态框
function showLoginModal() {
    const loginModal = document.getElementById('login-modal');
    if (!loginModal) return;
    ensureLoginModalOnTop();
    loginModal.style.display = 'block';
    // 复位一键登录按钮：成功后它停在 disabled/「登录中...」，
    // 登出再进登录页时必须回到初始态，否则永远点不动
    const oneClickBtn = document.getElementById('login-oneclick-btn');
    if (oneClickBtn) {
        oneClickBtn.disabled = false;
        oneClickBtn.textContent = '立即登录';
    }
    switchLoginTab('qr');
    getQRCode();
}
```

> **`showLoginModal()` 里的按钮复位是必须的，不是可选优化。** 一键登录成功后按钮停在 `disabled` + 「登录中...」；不复位的话，用户登出后重新打开登录页，按钮会永久卡在禁用态，一键登录再也点不动。这是实测确认过的缺陷。

> **`switchLoginTab()` 不能顺带取码。** 取码一旦搬进标签切换，会出现「首次打开双次取码」或「重登复用过期二维码且轮询不重启」两类回归。取码仍由 `showLoginModal()` 无条件调用。

---

### 3.7 `fmsa_django/static/css/main.css` —— 替换 1 个样式块

把原来的「登录模态框样式」整块替换掉。**注意保留 `.login-modal` 的 `z-index: 40000`**——它必须高于 `.metar-popup-overlay`(30000) 及其确认框(30001)，否则 token 失效时登录页会被未关闭的实况弹窗挡住。

**改动前**（整块）：

```css
/* 登录模态框样式
   必须高于实况弹窗(.metar-popup-overlay 30000)及其确认框(30001)，
   否则 token 失效时二维码会被未关闭的实况弹窗挡住。 */
.login-modal {
  background-color: rgba(0, 0, 0, 0.8);
  z-index: 40000;
}

.login-content {
  background-color: white;
  width: 400px;
  border-radius: 8px;
  text-align: center;
  margin-top: 140px;
}

.login-container {
  padding: 30px 20px;
}

.login-container h3 {
  color: #2c3e50;
  margin-bottom: 20px;
  font-size: 16px;
}

.qrcode-container {
  margin: 20px 0;
  padding: 15px;
  background-color: white;
  border: 1px solid #ddd;
  border-radius: 4px;
  display: inline-block;
}

.login-status {
  color: #666;
  font-size: 14px;
  margin-top: 15px;
}
```

**现在**（整块）：

```css
/* 登录页（全屏，视觉对齐 CAS 登录页）
   必须高于实况弹窗(.metar-popup-overlay 30000)及其确认框(30001)，
   否则 token 失效时登录页会被未关闭的实况弹窗挡住。 */
.login-modal {
  background-color: #fff;
  overflow: hidden;
  z-index: 40000;
}

.login-page {
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  overflow: auto;
  background-color: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 22px;
  padding: 24px;
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #2c3e50;
}

.login-brand-logo {
  width: 28px;
  height: 28px;
}

.login-brand-name {
  font-size: 16px;
  font-weight: 600;
}

.login-brand-abbr {
  font-size: 12px;
  color: #98a2b3;
  letter-spacing: 0.5px;
}

.login-card {
  width: 100%;
  max-width: 420px;
  background-color: #fff;
  border: 1px solid #eceff3;
  border-radius: 10px;
  padding: 28px 24px 24px;
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.06);
}

.login-title {
  margin: 0 0 18px;
  font-size: 20px;
  font-weight: 600;
  color: #1f2d3d;
  text-align: center;
}

.login-tabs {
  display: flex;
  justify-content: center;
  gap: 28px;
  border-bottom: 1px solid #eef1f5;
  margin-bottom: 22px;
}

.login-tab {
  background: none;
  border: 0;
  padding: 0 2px 10px;
  font-size: 15px;
  color: #6b7280;
  cursor: pointer;
  position: relative;
}

.login-tab.active {
  color: #e2231a;
  font-weight: 600;
}

.login-tab.active::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 2px;
  background: #e2231a;
  border-radius: 2px;
}

.login-panel {
  display: none;
}

.login-panel.active {
  display: block;
}

.qr-frame {
  position: relative;
  width: 200px;
  margin: 0 auto;
}

.qrcode-container {
  padding: 8px;
  background-color: #fff;
  border: 1px solid #e6e9ee;
  border-radius: 6px;
}

.login-hint {
  margin-top: 14px;
  font-size: 13px;
  color: #8a94a6;
  text-align: center;
}

.login-status {
  margin-top: 8px;
  font-size: 13px;
  color: #6b7280;
  text-align: center;
}

.login-tip-bar {
  width: 100%;
  max-width: 420px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background-color: #fff1f2;
  border: 1px solid #ffd9dc;
  border-radius: 8px;
  padding: 12px 16px;
}

.login-tip-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  color: #b42318;
}

.login-tip-text span {
  color: #8a94a6;
  font-size: 12px;
}

.login-tip-btn {
  background-color: #e2231a;
  color: #fff;
  border: 0;
  border-radius: 6px;
  padding: 8px 18px;
  font-size: 14px;
  cursor: pointer;
}

.login-tip-btn:disabled {
  background-color: #f3b4b0;
  cursor: not-allowed;
}

.login-footer {
  font-size: 12px;
  color: #b0b8c4;
  text-align: center;
}
```

> **`#qrcode-container` 会被整块 `innerHTML=` 覆盖**（`getQRCode()` / `expireQRCode()` 会重写它的内容）。所以任何装饰元素必须放在它的**兄弟节点** `.qr-frame` 里，放里面会被冲掉。

---

### 3.8 `fmsa_django/templates/web/index.html` —— 改 2 处

#### 3.8.1 登录区块改成全屏结构

**改动前**：

```html
<!-- 登录界面（仅current模式显示） -->
<div id="login-modal" class="modal login-modal" style="display: none;">
  <div class="modal-content login-content">
    <div class="login-container">
      <h3>请使用丰声扫码登录</h3>
      <div class="qrcode-container" id="qrcode-container">
        <img id="qrcode-image" src="" alt="二维码" style="width: 200px; height: auto;">
      </div>
      <div class="login-status" id="login-status">正在获取二维码...</div>
    </div>
  </div>
</div>
```

**现在**：

```html
<!-- 登录界面（仅current模式显示）：全屏 CAS 风格 -->
<div id="login-modal" class="modal login-modal" style="display: none;">
  <div class="login-page">

    <!-- 品牌区 -->
    <div class="login-brand">
      <img class="login-brand-logo" src="{% static 'svg/fmsa-favicon.svg' %}" alt="">
      <span class="login-brand-name">基于航班计划的气象监视告警系统</span>
      <span class="login-brand-abbr">FMSA</span>
    </div>

    <!-- 登录卡片 -->
    <div class="login-card">
      <h2 class="login-title">欢迎登录</h2>

      <div class="login-tabs" role="tablist">
        <button class="login-tab active" data-tab="qr" onclick="switchLoginTab('qr')" role="tab">扫码登录</button>
      </div>

      <!-- 扫码登录：保留既有 id，二维码轮询逻辑零改动 -->
      <div class="login-panel active" data-panel="qr">
        <div class="qr-frame">
          <div class="qrcode-container" id="qrcode-container">
            <img id="qrcode-image" src="" alt="二维码" style="width: 200px; height: auto;">
          </div>
        </div>
        <div class="login-hint">请使用 顺丰令牌 / 丰声APP或丰声Next 扫一扫登录</div>
        <div class="login-status" id="login-status">正在获取二维码...</div>
      </div>
    </div>

    <!-- 底部提示条：本机一键登录 -->
    <div class="login-tip-bar">
      <div class="login-tip-text">
        <strong>试试一键登录，更快更安全</strong>
        <span id="login-tip-usercode"></span>
      </div>
      <button class="login-tip-btn" id="login-oneclick-btn" onclick="doOneClickLogin()">立即登录</button>
    </div>

    <div class="login-footer">顺丰速运 版权所有 Copyright © 2013 sf-express.com Inc. All rights reserved.</div>
  </div>
</div>
```

> **`id="login-modal"` 与 `class="modal login-modal"` 必须保留**：`main.js` 里的 `canDismissModal` 白名单按这个 id 判断，改掉会导致「点遮罩/ESC 关不掉」和「挡不住实况弹窗」连锁回归。
>
> 品牌 logo 用的是 `{% static 'svg/fmsa-favicon.svg' %}`；若目标工程没有该文件，换成已有的 logo，或删掉 `<img>` 只留文字。

#### 3.8.2 注入两个配置项

**改动前**：

```html
  {% if test_time_iso %}
  window.testTimeISO = '{{ test_time_iso }}';
  {% endif %}
</script>
```

**现在**：

```html
  {% if test_time_iso %}
  window.testTimeISO = '{{ test_time_iso }}';
  {% endif %}
  // 一键登录：票据必须由本页在用户浏览器里取（身份取决于源 IP）
  window.sflinkBaseUrl = '{{ sflink_base_url }}';
  window.sflinkAppId = '{{ sflink_app_id }}';
</script>
```

---

### 3.9 `<FMSA>/.env` —— **追加** 6 个键

**不要覆盖整个 `.env`**（会冲掉对方已有的配置）。在文件末尾追加：

```dotenv
# 一键登录（sflink 链路）。SF_CAS_BASE_URL 是 CAS 站点根，
# SF_CAS_SERVICE_URL 是 CAS 的 service 参数（带 scheme 与端口，必须是这个形式）。
# 注意它与 SF_CAS_SERVICE_ID 不同：后者是裸主机名，只给 getConfig 当 serviceId 用。
SF_CAS_BASE_URL=https://cas.sf-express.com/cas
SF_CAS_SERVICE_URL=https://sfa-gwgw-inn.sf-airlines.com:8443
SF_SFLINK_BASE_URL=https://sflinksso.sf-express.com:54339
SF_SFLINK_APP_ID=55c450ff-33b6-4711-ad1c-e3b5d77b02f1
SF_CAS_APP_KEY=<从旧 cas_login.py 里写死的 appKey 原值迁出>
SF_CAS_APP_SECRET="<从旧 cas_login.py 里写死的 appSecret 原值迁出>"
```

三个必须注意的点：

1. **`SF_CAS_APP_SECRET` 的值含 `#`，必须加双引号。** 不加引号会被 dotenv 解析器当成行内注释**静默截断**。
2. **`SF_CAS_SERVICE_URL` 必须带 scheme + 端口**，与 `SF_CAS_SERVICE_ID`（裸主机名）**语义不同、不可互换**。传裸主机名会命中 CAS 的「安全级别更高，需二次校验」分支，拿不到 ST。
3. **不新增任何密码键。** 密码字段在 `sflinkTicket` 路径下不参与校验，模块内已写死固定串。

**旧的 7 个键保持不变**：`SF_INTRANET_BASE_URL` / `SF_CAS_VALIDATE_URL` / `SF_CAS_QRCODE_URL` / `SF_CAS_SCAN_URL` / `SF_CAS_CONFIG_URL` / `SF_CAS_SERVICE_ID` / `SF_CAS_LOGOUT_PATH`。

---
## 4. 验证

### 4.1 静态检查

```bash
cd <FMSA>/fmsa_django
python -m py_compile api/sflink_login.py api/cas_login.py api/views.py api/urls.py web/views.py
node --check static/js/main.js
```

### 4.2 文件完整性

逐个比对第 2 节表格里的 **大小** 与 **SHA256 前 16 位**。全中即为改到位。

### 4.3 接口级

| 用例 | 期望 |
|---|---|
| `POST /current/api/auth/one-click-login/`，body 为空 | HTTP 400，`{"success": false, "error": "缺少 sflink 票据"}` |
| `POST /current/api/auth/one-click-login/`，`{"ticket": ""}` | HTTP 400，同上 |
| `POST /test/api/auth/one-click-login/` | HTTP 400，「此接口仅用于current模式」 |
| `POST /current/api/auth/get-qrcode/`（扫码入口回归） | HTTP 200，返回二维码 base64 |

### 4.4 浏览器实测（**必做，静态检查替代不了**）

1. 打开首页，登录页应为**全屏**，底部有「试试一键登录，更快更安全 / 立即登录」。
2. 打开浏览器控制台，执行 `fetchSflinkTicket().then(t => console.log(t.length))`——应打印一个三位数长度（约 540），说明**跨域取票据可行**（sflinksso 的 CORS 是开放的）。
3. 点「立即登录」：按钮变「登录中...」→ 登录页消失 → 页面加载出数据。
4. 检查 `localStorage` 里有 token，且 `userCode` 与取到的票据 JWT 里的 `sub` **一致**。
5. **登出，再重新打开登录页**：按钮应恢复为可点击的「立即登录」（验证 3.6.2 的复位逻辑）。

### 4.5 已知的未验证假设（**上服务器前必须验**）

服务端拿**用户机器取的**票据去 CAS 换 ST（链路第 ④ 步）——**CAS 是否校验提交方 IP 与票据来源一致**，本机无法验证（改不了源 IP）。

从 CAS 页面自身做法看不像是会校验：`deviceid` 只被存进 cookie `sflinkDeviceId` 供后续用，提交表单时并未回传。但这是推断。

**真正部署到服务器前，必须拿两台机器验一次。** 若 CAS 确实绑 IP，这条路走不通，只能退回「跳转到真实 CAS 登录页」。

---

## 5. 回退

改动前先备份这 9 个文件（`.env` 单独备份），出问题直接覆盖回去即可：

```
fmsa_django/api/sflink_login.py      （新增，回退=删除）
fmsa_django/api/cas_login.py
fmsa_django/api/urls.py
fmsa_django/api/views.py
fmsa_django/web/views.py
fmsa_django/static/js/main.js
fmsa_django/static/css/main.css
fmsa_django/templates/web/index.html
.env
```

前端资源（`main.js` / `main.css`）有改动，回退后**必须清浏览器缓存**，否则会加载到旧版本。

---

## 6. 执行顺序建议

1. 第 1 节前置检查（不满足就停）
2. 备份 9 个文件
3. 3.1 新建 `sflink_login.py`
4. 3.2 `cas_login.py`（先做，因为 `sflink_login.py` 依赖它的 `gateway_credentials`）
5. 3.3 `urls.py` / 3.4 `views.py` / 3.5 `web/views.py`
6. 3.6 `main.js` / 3.7 `main.css` / 3.8 `index.html`
7. 3.9 `.env` 追加 6 键
8. 第 4 节验证

---

## 附录 A：如果目标的工程目录是 `mtws_django`

**不要按本文档改。** 那是另一条支线，差异是结构性的：

| | 本文档适用（`fmsa_django`） | 另一支（`mtws_django`） |
|---|---|---|
| 工程目录 | `fmsa_django` | `mtws_django` |
| 配置模块 | `utils/sf_env.py` → `env` / `require` / `intranet_url` | `mtws_system/env.py` → `env_str` / `env_required` / …（**另一套 API**） |
| `cas_login.py` | 5,414 B，扫码换票 | 12,603 B，**浏览器跳转 + 代理换票**，是完全不同的实现 |
| 登录提示条 | 有（`login-tip-btn`） | 无 |
| `switchLoginTab` | 有 | 无 |

在那一支上要做的不是「覆盖」，是「移植适配」：需要先把 CAS 登录的语义对齐（那一支走浏览器跳转拿 `?ticket=`，本文档这条链路是服务端拿 sflink 票据换 ST），再谈一键登录。

**判断方法**：看 Django 工程目录名，或者看 `manage.py` 所在目录。

---

## 附录 B：参考实现

同目录另有一份 4 步流程的参考实现（**非浏览器流程**，仅供对照协议细节，不要直接照抄）：

```
<FMSA>/package/dist/auth.js
```

---

## 附录 C：本轮不做的（避免 AI 自行扩大范围）

- 不做 `fsnext` 通道（需本机安装丰声Next 客户端）
- 不做多账号选择 UI
- 不做服务端缓存票据或复用 ST
- 不在 `#login-tip-usercode` 展示工号
- 不做失败自动重试
- 不重构扫码路径（保留其内联代码，不强行抽成 `handleLoginSuccess`）
