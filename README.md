# WorkBuddy 自动签到

通过 GitHub Actions 定时调用 WorkBuddy 的每日签到接口，自动领取「Buddy加油站」积分。

## 定时规则

`cron: '0 0,4,15 * * *'`（UTC）＝ 北京时间 **08:00 / 12:00 / 23:00**，每天三次。
支持在 Actions 页面手动触发（`workflow_dispatch`）。

## 配置

在 `Settings → Secrets and variables → Actions` 中添加：

| Secret | 必填 | 说明 |
| --- | --- | --- |
| `WORKBUDDY_REFRESH_TOKEN` | 是 | 格式 `手机号:accessToken:refreshToken` |
| `PUSHPLUS_TOKEN` | 否 | 配了就推送微信通知，不配只写日志 |

`WORKBUDDY_REFRESH_TOKEN` 的获取方式：双击桌面 `获取凭证.bat`，
它会读取本机 WorkBuddy 的登录态并把整串凭证复制到剪贴板，直接粘贴即可。

## 推送格式

每条微信通知的正文尾部都会自动附上来源与凭证状态：

```
签到成功！本次获得 100 积分，连续签到 3 天，累计 300 积分

----------------------
来源：GitHub Actions · WorkBuddy 自动签到
运行记录：https://github.com/yu-echo/workbuddy_checkin/actions/runs/123456
Token 认证日期：2026-09-17
凭证有效期至 2026-11-17（剩 59 天）
```

- **来源**：在 GitHub Actions 里显示 `GitHub Actions` 并附运行记录链接；
  在本机直接运行则显示 `本地运行`，便于区分消息是谁发的。
- **Token 认证日期**：取 JWT 的 `auth_time`，即账号真实登录认证的时刻。
  注意它与令牌刷新无关——刷新会改写 `iat`/`exp`，但 `auth_time` 保持不变。
- **凭证有效期**：取 `refreshToken` 的 `exp`，也就是必须重跑 `获取凭证.bat` 的最后期限。

## 脚本说明

脚本会先查签到状态（幂等，重复运行不会重复领取），未签到才调用签到接口。
每次运行会用 `refreshToken` 换取新的 `accessToken`，因此只要 `refreshToken`
本身没过期，就不需要手动更新 Secret。

## 凭证过期

`refreshToken` 有效期约 60 天。脚本会在剩余不足 7 天时通过 PushPlus 提醒，
收到提醒后重新执行一次 `获取凭证.bat` 并更新 Secret 即可。

失败排查时看 Actions 日志里的这几行：

- `[Token刷新] 成功获取新的 accessToken` → 刷新链路正常
- `[成功] 签到成功！...` → 签到成功
- `[跳过] 今日已签到` → 今天已经领过了
- `⚠️ WorkBuddy 登录态失效` → 凭证过期，需要重新获取

## 接口备注

实测使用的接口（`www.workbuddy.cn`，`www.codebuddy.cn` 同样可用）：

| 用途 | 方法 | 路径 |
| --- | --- | --- |
| 刷新令牌 | POST | `/v2/plugin/auth/token/refresh` |
| 查询状态 | POST | `/v2/billing/meter/checkin-activity-status` |
| 执行签到 | POST | `/v2/billing/meter/daily-checkin` |

刷新令牌需要 `X-Refresh-Token` 头，其余接口需要 `Authorization: Bearer`、
`X-User-Id`、`X-Domain` 头；业务成功判据为响应体 `code == 0`。
