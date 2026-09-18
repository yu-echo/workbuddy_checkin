# WorkBuddy 自动签到

用 GitHub Actions 每天自动完成 WorkBuddy「Buddy加油站」签到，结果通过微信推送。

不需要服务器，不需要装依赖，配两个 Secret 就能跑。

## 它是怎么工作的

WorkBuddy 的签到接口没有公开文档，下面是**实测出来的**端点（网上流传的版本大多是错的，见文末「踩过的坑」）。

| 用途 | 方法 | 路径 |
| --- | --- | --- |
| 刷新令牌 | `POST` | `https://www.workbuddy.cn/v2/plugin/auth/token/refresh` |
| 查询状态 | `POST` | `/v2/billing/meter/checkin-activity-status` |
| 执行签到 | `POST` | `/v2/billing/meter/daily-checkin` |

几个关键点：

- 三个接口**都是 POST**，请求体都是 `{}`。
- 刷新令牌走**请求头**而不是 body：`X-Refresh-Token` + `X-Auth-Refresh-Source: plugin`。
- 其余接口需要 `Authorization: Bearer <accessToken>` + `X-User-Id` + `X-Domain`。
- 成功判据是响应体 `code == 0`。
- 已签到时返回 `{"code":10001,"msg":"今天已签到，请明天再来"}` —— 这是**正常**情况，不是失败。
- `www.codebuddy.cn` 与 `www.workbuddy.cn` 等价可用。

每次运行的流程是：先拿 `refreshToken` 换新的 `accessToken`，再查签到状态（幂等，重复运行不会多领），
只有未签到才真正调用签到接口。

## 部署

### 1. 拿凭证

双击桌面 `获取凭证.bat`，它读取本机 WorkBuddy 的登录态，
把 `手机号:accessToken:refreshToken` 复制到剪贴板。

### 2. 配 Secrets

`Settings → Secrets and variables → Actions → New repository secret`：

| Secret | 必填 | 说明 |
| --- | --- | --- |
| `WORKBUDDY_REFRESH_TOKEN` | 是 | 上一步的 `手机号:AT:RT`，整串粘贴 |
| `PUSHPLUS_TOKEN` | 否 | 配了才推微信，不配只写日志 |

### 3. 跑一次

`Actions → WorkBuddy 自动签到 → Run workflow`。

GitHub 的定时任务需要先手动触发一次才会激活。

## 定时规则

```
cron: '0 0,4,15 * * *'    # UTC
```

即北京时间 **08:00 / 12:00 / 23:00**，每天三次。跑三次是为了防漏，
重复领取由脚本的幂等检查挡住。

工作流里还有个「保活提交」步骤：GitHub 会在仓库 60 天无活动时停用定时任务，
所以每 45 天自动提交一次空文件。这需要写权限，已在 yml 里声明 `permissions: contents: write`。

## 推送格式

```
标题：🎉 WorkBuddy 签到成功

签到成功！本次获得 100 积分，连续签到 3 天，累计 200 积分

----------------------
来源：GitHub Actions · WorkBuddy 自动签到
运行记录：https://github.com/yu-echo/workbuddy_checkin/actions/runs/123456
Token 认证日期：2026-09-17
凭证有效期至 2026-11-17（剩 59 天）
```

- **来源**自动识别：在 Actions 里显示 `GitHub Actions` 并附运行记录直达链接；
  在本机直接运行显示 `本地运行`，不会谎报是 CI 发的。
- **Token 认证日期**取 JWT 的 `auth_time`，即账号真实登录认证的时刻。
  注意不是 `iat`——`iat` 每次刷新都变，用它的话这行永远显示当天，等于没有。
- **凭证有效期**取 `refreshToken` 的 `exp`。

三种状态都会推送：签到成功、今日已签到、登录态失效需要重新取凭证。

## 凭证过期

`refreshToken` 有效期约 60 天。剩余不足 7 天时脚本会推送提醒，
收到后重跑一次 `获取凭证.bat` 并更新 `WORKBUDDY_REFRESH_TOKEN` 即可。

日志排查对照：

| 日志 | 含义 |
| --- | --- |
| `[Token刷新] 成功获取新的 accessToken` | 刷新链路正常 |
| `[成功] 签到成功！...` | 签到成功 |
| `[跳过] 今日已签到` | 今天已经领过了，正常 |
| `⚠️ WorkBuddy 登录态失效` | 凭证过期，需要重新获取 |

## 安全

- 两个 Secret 只存在于 GitHub 的加密存储，**不在代码、不在 git 历史、不在日志明文**，
  日志里自动打码成 `***`。
- 日志里的手机号**已脱敏**（`176****2416`）。Actions 日志在公开仓库里对所有登录用户可见，
  完整手机号不应出现在那里。
- 打印接口响应体前会先抹掉 `accessToken` / `refreshToken` 等字段（见 `sanitize_payload()`）。
  直接打印原始响应是典型的令牌泄露写法。

## 踩过的坑

网上流传的 WorkBuddy 签到脚本，接口和调用方式基本都是猜的，**没有一个能跑通**：

| 常见写法 | 实际情况 |
| --- | --- |
| `GET /v2/billing/meter/checkin-activity-status` | 404，必须用 POST |
| `POST /v2/auth/refresh-token` | 404，真实路径完全不同 |
| `Authorization: Bearer 手机号:AT:RT` | 401，整串不是 token |
| 判断 `code == 10001`、`data.checked` | 字段不存在；状态字段是 `today_checked_in` |

手上的版本跑不通时，先对照上表核对端点和请求头。

## License

MIT
