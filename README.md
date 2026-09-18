<!-- markdownlint-disable MD033 MD041 -->

<div align="center">
  <h1>🤖 WorkBuddy 自动签到</h1>
  <img alt="license" src="https://img.shields.io/github/license/yu-echo/workbuddy_checkin">
  <img alt="platform" src="https://img.shields.io/badge/platform-GitHub%20Actions-blueviolet">
  <img alt="python" src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white">
  <img alt="deps" src="https://img.shields.io/badge/dependencies-%E9%9B%B6-brightgreen">
  <img alt="commit" src="https://img.shields.io/github/commit-activity/m/yu-echo/workbuddy_checkin">
  <img alt="stars" src="https://img.shields.io/github/stars/yu-echo/workbuddy_checkin?style=social">
</div>

---

用 **GitHub Actions** 每天自动完成 WorkBuddy「Buddy加油站」签到，结果推送到微信。

不需要服务器、不需要装依赖、不需要本地常驻——配两个 Secret 就能跑，跑完自动汇报。

✨ 如果这个项目帮到你，欢迎在右上角点亮 Star ✨

---

## 功能介绍

### 🌿 日常签到

- 🎯 自动完成「Buddy加油站」每日签到，领取积分
- 🔁 **幂等设计**：先查状态再签到，一天跑三次也不会重复领取
- 🔑 **自动续期**：每次运行用 `refreshToken` 换新的 `accessToken`，不用手动维护

### 📱 结果推送

- ✅ 签到成功 → 推送本次获得积分、连续天数、累计积分
- 😴 今日已签到 → 推送「已签到」，不报错
- ⚠️ 登录态失效 / 凭证即将过期 → 主动提醒该重新取凭证了

### 🛡️ 安全

- 🔒 凭证只存 GitHub 加密 Secret，**不在代码、不在 git 历史、不在日志明文**
- 🙈 日志里的手机号脱敏显示（`176****2416`）
- 🧹 打印接口响应前先抹掉令牌字段，避免「排查日志顺手上传凭据」这种事

---

## 效果预览

微信收到的通知长这样：

```
🎉 WorkBuddy 签到成功

签到成功！本次获得 100 积分，连续签到 3 天，累计 200 积分

----------------------
来源：GitHub Actions · WorkBuddy 自动签到
运行记录：https://github.com/yu-echo/workbuddy_checkin/actions/runs/123456
Token 认证日期：2026-09-17
凭证有效期至 2026-11-17（剩 59 天）
```

- **来源**会自动识别：Actions 里显示 `GitHub Actions` 并附运行记录直达链接；
  在本机直接运行则显示 `本地运行`，不会谎报是 CI 发的。
- **Token 认证日期**取 JWT 的 `auth_time`，即账号真实登录认证的时刻。
  注意它不是 `iat` —— `iat` 每次刷新都变，用它的话这行永远显示当天，等于没有。
- **凭证有效期**取 `refreshToken` 的 `exp`，也就是下一次该重新取凭证的时间。

---

## 使用说明

### 1. 拿到凭证

双击桌面 `获取凭证.bat`，它读取本机 WorkBuddy 的登录态，
把 `手机号:accessToken:refreshToken` 复制到剪贴板。

### 2. 配置 Secrets

`Settings → Secrets and variables → Actions → New repository secret`：

| Secret | 必填 | 说明 |
| --- | --- | --- |
| `WORKBUDDY_REFRESH_TOKEN` | ✅ | 上一步的 `手机号:AT:RT`，整串粘贴 |
| `PUSHPLUS_TOKEN` | ⭕ | 配了才推微信，不配只写日志 |

### 3. 跑一次

`Actions → WorkBuddy 自动签到 → Run workflow`。

> GitHub 的定时任务需要先手动触发一次才会激活。

### 4. 定时规则

```
cron: '0 0,4,15 * * *'    # UTC
```

即北京时间 **08:00 / 12:00 / 23:00**，每天三次。跑三次是为了防漏，
重复领取由脚本的幂等检查挡住。

> 工作流里还有个「保活提交」步骤：GitHub 会在仓库 60 天无活动时停用定时任务，
> 所以每 45 天自动提交一次空文件。这需要写权限，已在 yml 里声明 `permissions: contents: write`。

---

## 接口说明

WorkBuddy 的签到接口没有公开文档，下面这些端点是**实测出来的**。

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

---

## 常见问题

### 网上流传的脚本为什么跑不通

那些版本的接口和调用方式基本都是猜的，**没有一个能跑通**：

| 常见写法 | 实际情况 |
| --- | --- |
| `GET /v2/billing/meter/checkin-activity-status` | 404，必须用 POST |
| `POST /v2/auth/refresh-token` | 404，真实路径完全不同 |
| `Authorization: Bearer 手机号:AT:RT` | 401，整串不是 token |
| 判断 `code == 10001`、`data.checked` | 字段不存在；状态字段是 `today_checked_in` |

手上的版本跑不通时，先对照上表核对端点和请求头。

### 凭证过期怎么办

`refreshToken` 有效期约 60 天。剩余不足 7 天时脚本会推送提醒，
收到后重跑一次 `获取凭证.bat` 并更新 `WORKBUDDY_REFRESH_TOKEN` 即可。

### 日志怎么看

| 日志 | 含义 |
| --- | --- |
| `[Token刷新] 成功获取新的 accessToken` | 刷新链路正常 |
| `[成功] 签到成功！...` | 签到成功 |
| `[跳过] 今日已签到` | 今天已经领过了，正常 |
| `⚠️ WorkBuddy 登录态失效` | 凭证过期，需要重新获取 |

---

## 安全说明

- 两个 Secret 只存在于 GitHub 的加密存储，**不在代码、不在 git 历史、不在日志明文**，
  运行日志里会自动打码成 `***`。
- 日志里的手机号**已脱敏**（`176****2416`）。Actions 日志在公开仓库中
  对所有登录 GitHub 的用户可见，完整手机号不应出现在那里。
- 打印接口响应体前会先抹掉 `accessToken` / `refreshToken` 等字段（见 `sanitize_payload()`）。
  直接打印原始响应是典型的令牌泄露写法。
- 仓库可以放心设为公开：不存在任何硬编码凭据，Secret 也不会随仓库分发。

---

## 鸣谢

- 签到接口的端点与请求头来自对客户端网络请求的实测抓取
- 推送通道使用 **[PushPlus](https://www.pushplus.plus/)**

---

## License

[MIT](./LICENSE)

<p align="center">
  <sub>Made with ❤️ for personal automation</sub>
</p>
