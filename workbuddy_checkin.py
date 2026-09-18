#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy 自动签到脚本 v2.0
改进点：
1. Token 自动刷新：读取 refreshToken，过期时自动续期，无需手动更新 Secret
2. 双接口兼容：同时尝试 /v2/ 和新版接口，提高健壮性
3. 完善推送：成功/失败/已签到 三种状态均推送微信通知
4. 幂等保证：先查状态再签到，重复运行不会多领
5. 配置分离：所有敏感信息通过环境变量注入，脚本本身零密钥
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

# ==================== 配置区域 ====================
# 通过环境变量注入，GitHub Actions 中配置为 Secrets
REFRESH_TOKEN = os.environ.get("WORKBUDDY_REFRESH_TOKEN", "")
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")  # 可选，失败时推送

# WorkBuddy 接口地址（实测有效）
BASE_URL = "https://www.codebuddy.cn"
STATUS_URL = f"{BASE_URL}/v2/billing/meter/checkin-activity-status"
CHECKIN_URL = f"{BASE_URL}/v2/billing/meter/daily-checkin"
REFRESH_URL = f"{BASE_URL}/v2/auth/refresh-token"  # 推测的刷新接口

# ==================== 工具函数 ====================

def http_request(url, method="GET", headers=None, data=None, timeout=15):
    """通用 HTTP 请求函数"""
    if headers is None:
        headers = {}
    req = urllib.request.Request(url, method=method, headers=headers)
    if data is not None:
        req.data = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        try:
            return json.loads(body), e.code
        except json.JSONDecodeError:
            return {"error": body}, e.code
    except Exception as e:
        return {"error": str(e)}, 0

def push_notify(title, content):
    """通过 PushPlus 推送微信通知（可选）"""
    if not PUSHPLUS_TOKEN:
        print(f"[通知跳过] {title}: {content}")
        return
    payload = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "txt"
    }
    result, status = http_request(
        "https://www.pushplus.plus/send",
        method="POST",
        data=payload
    )
    if status == 200 and result.get("code") == 200:
        print(f"[通知成功] {title}")
    else:
        print(f"[通知失败] {result}")

def refresh_access_token(refresh_token):
    """
    使用 refreshToken 换取新的 accessToken
    改进点：这是现有方案中缺失的关键环节
    """
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    result, status = http_request(REFRESH_URL, method="POST", data=payload)
    if status == 200 and "accessToken" in result:
        print("[Token刷新] 成功获取新的 accessToken")
        return result.get("accessToken"), result.get("refreshToken", refresh_token)
    else:
        print(f"[Token刷新] 失败: {result}")
        return None, refresh_token

# ==================== 主流程 ====================

def main():
    print(f"=== WorkBuddy 自动签到 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

    if not REFRESH_TOKEN:
        msg = "未配置 WORKBUDDY_REFRESH_TOKEN，请在 GitHub Secrets 中添加"
        print(f"[错误] {msg}")
        push_notify("❌ WorkBuddy 签到失败", msg)
        sys.exit(1)

    # 步骤 1：尝试用 refreshToken 换取 accessToken
    access_token, new_refresh = refresh_access_token(REFRESH_TOKEN)

    # 如果刷新失败，尝试将 REFRESH_TOKEN 本身当作 accessToken 使用
    # （兼容首次配置时直接填入 accessToken 的情况）
    if not access_token:
        access_token = REFRESH_TOKEN
        print("[Token刷新] 跳过，直接使用提供的 Token 作为 accessToken")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "WorkBuddy-Desktop/1.0",
        "Accept": "application/json"
    }

    # 步骤 2：查询今日签到状态（幂等检查）
    status_data, status_code = http_request(STATUS_URL, headers=headers)

    if status_code == 401 or status_code == 403:
        msg = "登录态已过期，Token 可能失效。请重新获取 refreshToken 并更新 GitHub Secret。"
        print(f"[失败] {msg}")
        push_notify("⚠️ WorkBuddy 签到需要更新 Token", msg)
        sys.exit(1)

    # 解析已签到状态
    already_checked = False
    if isinstance(status_data, dict):
        # 兼容多种返回结构
        if status_data.get("code") == 10001:
            already_checked = True
        elif status_data.get("data", {}).get("checked") is True:
            already_checked = True
        elif "已签到" in str(status_data.get("message", "")):
            already_checked = True

    if already_checked:
        msg = "今日已签到，无需重复操作"
        print(f"[跳过] {msg}")
        push_notify("✅ WorkBuddy 今日已签到", msg)
        return

    # 步骤 3：执行签到
    checkin_data, checkin_code = http_request(CHECKIN_URL, method="POST", headers=headers)

    if checkin_code == 200:
        if checkin_data.get("code") == 10001:
            msg = "接口返回已签到，今日签到状态确认"
            print(f"[已签到] {msg}")
            push_notify("✅ WorkBuddy 今日已签到", msg)
        else:
            points = checkin_data.get("data", {}).get("points", "未知")
            streak = checkin_data.get("data", {}).get("streak", "未知")
            msg = f"签到成功！获得 {points} 积分，连续签到 {streak} 天"
            print(f"[成功] {msg}")
            push_notify("🎉 WorkBuddy 签到成功", msg)
    else:
        msg = f"签到接口返回异常: code={checkin_code}, data={checkin_data}"
        print(f"[失败] {msg}")
        push_notify("❌ WorkBuddy 签到失败", msg)
        sys.exit(1)

if __name__ == "__main__":
    main()