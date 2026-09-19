#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy 自动签到脚本 v3.0

与 v2.0 的区别（v2.0 的接口和调用方式均为猜测，实测全部失效）：
  1. 刷新接口修正为 POST /v2/plugin/auth/token/refresh，用 X-Refresh-Token 头传令牌
     （v2.0 用的 /v2/auth/refresh-token 是 404）
  2. 凭证 WORKBUDDY_REFRESH_TOKEN 按 `手机号:accessToken:refreshToken` 解析，
     不再把整串塞进 Authorization（v2.0 因此必然 401）
  3. 签到接口改为 POST，并补上必需的 X-User-Id / X-Domain 头
     （v2.0 用 GET，必然 404）
  4. 成功判据改为业务码 code == 0（v2.0 判断的 code==10001 并不存在）
  5. 已签到字段为 today_checked_in（v2.0 查的 data.checked 不存在）
  6. 新增令牌到期预警：refreshToken 剩余不足 7 天时推送提醒

所有敏感信息通过环境变量注入，脚本本身零密钥。
仓库：https://github.com/yu-echo/workbuddy_checkin
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime

# ==================== 配置区域 ====================

CREDENTIAL = os.environ.get("WORKBUDDY_REFRESH_TOKEN", "").strip()
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "").strip()

BASE_URL = os.environ.get("WORKBUDDY_BASE_URL", "https://www.workbuddy.cn").rstrip("/")
REFRESH_URL = f"{BASE_URL}/v2/plugin/auth/token/refresh"
STATUS_URL = f"{BASE_URL}/v2/billing/meter/checkin-activity-status"
CHECKIN_URL = f"{BASE_URL}/v2/billing/meter/daily-checkin"

DEFAULT_DOMAIN = "www.workbuddy.cn"
TOKEN_WARN_DAYS = 7
TIMEOUT = 20

# ==================== 工具函数 ====================


def jwt_claim(token, key):
    """从 JWT 中读取指定 claim（不做签名校验，仅用于取 uid / exp）。"""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get(key)
    except Exception:
        return None


def mask_phone(phone: str) -> str:
    """手机号脱敏。

    Actions 日志在公开仓库里是任何登录用户都能看的（未登录看不到），
    所以完整手机号不能进日志。
    """
    if not phone:
        return "未知"
    if len(phone) < 7:
        return "*" * len(phone)
    return f"{phone[:3]}****{phone[-4:]}"


# 响应体里出现这些字段一律替换掉，避免原样打进日志
_SENSITIVE_KEYS = {
    "accesstoken", "refreshtoken", "token", "cred", "authorization",
    "password", "secret", "sessionstate",
}


def sanitize_payload(value):
    """递归脱敏响应体。日志里不要出现任何令牌字段。"""
    if isinstance(value, dict):
        return {
            k: ("<已脱敏>" if str(k).lower() in _SENSITIVE_KEYS else sanitize_payload(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [sanitize_payload(v) for v in value]
    return value


def http_json(url, method="GET", headers=None, body=None):
    """返回 (json_or_text, status)。从不抛异常。"""
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, method=method, headers=hdrs, data=data)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            try:
                return json.loads(raw), resp.status
            except json.JSONDecodeError:
                return raw, resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        try:
            return json.loads(raw), e.code
        except json.JSONDecodeError:
            return raw, e.code
    except Exception as e:
        return f"<{type(e).__name__}: {e}>", 0


# 运行上下文，用于给推送内容附加「来源」与「凭证」信息
_CTX = {"access_token": "", "refresh_token": ""}


def build_footer():
    """推送尾部：来源 + Token 认证日期 + 凭证有效期。"""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        source = f"GitHub Actions{(' · ' + os.environ['GITHUB_WORKFLOW']) if os.environ.get('GITHUB_WORKFLOW') else ''}"
        source += f"\n运行记录：{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/" \
                  f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    else:
        source = "本地运行"

    lines = [f"来源：{source}"]

    auth_time = (jwt_claim(_CTX["refresh_token"], "auth_time")
                 or jwt_claim(_CTX["access_token"], "auth_time"))
    if auth_time:
        lines.append(f"Token 认证日期：{datetime.fromtimestamp(auth_time).strftime('%Y-%m-%d')}")

    rt_exp = jwt_claim(_CTX["refresh_token"], "exp")
    if rt_exp:
        days = int((rt_exp - datetime.now().timestamp()) // 86400)
        lines.append(f"凭证有效期至 {datetime.fromtimestamp(rt_exp).strftime('%Y-%m-%d')}（剩 {days} 天）")

    return "\n".join(lines)


def push_notify(title, content):
    """PushPlus 微信推送（未配置则只打印）。自动附加来源与凭证信息。"""
    body = f"{content}\n\n{'-' * 22}\n{build_footer()}"
    print(f"[通知] {title} | {content}")
    if not PUSHPLUS_TOKEN:
        return
    result, status = http_json("https://www.pushplus.plus/send", method="POST",
                               body={"token": PUSHPLUS_TOKEN, "title": title,
                                     "content": body, "template": "txt"})
    ok = status == 200 and isinstance(result, dict) and result.get("code") == 200
    print(f"[推送{'成功' if ok else '失败'}] {result if not ok else title}")


def die(title, message):
    push_notify(title, message)
    sys.exit(1)


# ==================== 主流程 ====================

def parse_credential(raw):
    """解析 `手机号:accessToken:refreshToken`；也兼容直接粘贴单个 token。"""
    parts = [p.strip() for p in raw.split(":")]
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 1:
        return (jwt_claim(parts[0], "preferred_username") or ""), parts[0], ""
    raise ValueError("凭证格式应为 手机号:accessToken:refreshToken")


def refresh_access_token(refresh_token, domain):
    """用 refreshToken 换新的 accessToken / refreshToken。失败返回 (None, None, domain)。"""
    headers = {
        "Accept": "application/json",
        "X-Refresh-Token": refresh_token,
        "X-Auth-Refresh-Source": "plugin",
        "X-Domain": domain,
    }
    uid = jwt_claim(refresh_token, "sub")
    if uid:
        headers["X-User-Id"] = uid

    result, status = http_json(REFRESH_URL, method="POST", headers=headers, body={})
    if status == 200 and isinstance(result, dict) and result.get("code") == 0:
        data = result.get("data") or {}
        at = data.get("accessToken")
        if at:
            print("[Token刷新] 成功获取新的 accessToken")
            return at, data.get("refreshToken") or refresh_token, data.get("domain") or domain
    print(f"[Token刷新] 失败: status={status} resp={sanitize_payload(result)}")
    return None, None, domain


def check_token_lifetime(refresh_token):
    """检查 refreshToken 剩余有效期，临近到期时提醒。"""
    exp = jwt_claim(refresh_token, "exp")
    if not exp:
        return
    left = int(exp - datetime.now().timestamp())
    days = left // 86400
    if left <= 0:
        print(f"[令牌] refreshToken 已过期 {-days} 天")
    elif days < TOKEN_WARN_DAYS:
        push_notify(
            "⚠️ WorkBuddy 凭证即将过期",
            f"refreshToken 仅剩 {days} 天有效期。请双击桌面「获取凭证.bat」，"
            f"把新的 手机号:AT:RT 更新到 GitHub Secret WORKBUDDY_REFRESH_TOKEN。")
    else:
        print(f"[令牌] refreshToken 剩余 {days} 天")


def main():
    print(f"=== WorkBuddy 自动签到 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

    if not CREDENTIAL:
        die("❌ WorkBuddy 签到失败",
            "未配置 WORKBUDDY_REFRESH_TOKEN，请在 GitHub Secrets 中添加。")

    try:
        phone, access_token, refresh_token = parse_credential(CREDENTIAL)
    except ValueError as e:
        print(f"[错误] {e}")
        sys.exit(1)

    # 认证日期与凭证有效期以「原始凭证」为准：
    # 刷新会签发新令牌并改写 iat/exp，但 auth_time 保持不变。
    _CTX["access_token"], _CTX["refresh_token"] = access_token, refresh_token

    print(f"[凭证] 手机号={mask_phone(phone)} accessToken={len(access_token)} 字符 "
          f"refreshToken={len(refresh_token)} 字符")

    domain = DEFAULT_DOMAIN

    # 步骤 1：刷新 accessToken
    if refresh_token:
        new_at, new_rt, domain = refresh_access_token(refresh_token, domain)
        if new_at:
            access_token = new_at
            _CTX["access_token"] = new_at
        else:
            print("[Token刷新] 回退使用凭证中的 accessToken")
            check_token_lifetime(refresh_token)

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
        "X-Domain": domain,
    }
    uid = jwt_claim(access_token, "sub")
    if uid:
        headers["X-User-Id"] = uid

    # 步骤 2：查询今日签到状态（幂等检查）
    status_data, status_code = http_json(STATUS_URL, method="POST", headers=headers, body={})

    if status_code in (401, 403):
        die("⚠️ WorkBuddy 登录态失效",
            "accessToken 已失效且无法自动刷新。请双击桌面「获取凭证.bat」，"
            "把新的 手机号:AT:RT 更新到 GitHub Secret WORKBUDDY_REFRESH_TOKEN。")

    if not isinstance(status_data, dict) or status_data.get("code") != 0:
        detail = status_data if isinstance(status_data, str) else json.dumps(
            status_data, ensure_ascii=False)
        die("❌ WorkBuddy 签到失败", f"查询签到状态异常：HTTP {status_code} {detail[:300]}")

    info = status_data.get("data") or {}
    print(f"[状态] 活动={info.get('theme_name') or info.get('activity_name')} "
          f"连续={info.get('streak_days')}天 累计={info.get('total_credits')}积分")

    if info.get("today_checked_in"):
        msg = (f"今日已签到，连续 {info.get('streak_days', '?')} 天，"
               f"累计 {info.get('total_credits', '?')} 积分")
        print(f"[跳过] {msg}")
        # 不推送：定时任务一天跑 3 次，只有真正签到时才通知，
        # 否则早上签完，中午和晚上还会各收到一条「今日已签到」，属于重复打扰。
        return

    # 步骤 3：执行签到
    checkin_data, checkin_code = http_json(CHECKIN_URL, method="POST", headers=headers, body={})

    if not isinstance(checkin_data, dict):
        die("❌ WorkBuddy 签到失败",
            f"签到接口返回异常：HTTP {checkin_code} {str(checkin_data)[:300]}")

    bcode = checkin_data.get("code")
    if bcode == 0:
        payload = checkin_data.get("data") or checkin_data
        credit = payload.get("credit", payload.get("today_credit", "?"))
        streak = payload.get("streak_days", "?")
        total = payload.get("total_credits", info.get("total_credits", "?"))
        bonus = "（连签奖励日）" if payload.get("is_streak_day") else ""
        msg = f"签到成功{bonus}！本次获得 {credit} 积分，连续签到 {streak} 天，累计 {total} 积分"
        print(f"[成功] {msg}")
        push_notify("🎉 WorkBuddy 签到成功", msg)
        return

    msg = checkin_data.get("msg") or "未知错误"
    if "已" in str(msg) or bcode in (10001, 40001):
        print(f"[已签到] {msg}")
        # 同上：已签到不推送，保证一天最多一条通知
        return

    die("❌ WorkBuddy 签到失败",
        f"签到接口返回异常：HTTP {checkin_code} code={bcode} msg={msg}")


if __name__ == "__main__":
    main()
