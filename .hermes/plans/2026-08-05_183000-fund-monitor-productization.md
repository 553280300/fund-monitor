# Fund Monitor Productization Plan

> **Goal:** 把现有的个人基金监控脚本包装成一个可交付的「净值监控 + 异动提醒」服务，发给用户就能用。

**现有资产：**
- `fund_monitor.py` — 数据采集（腾讯财经 + Yahoo Finance）+ 涨跌幅阈值判断 + 推送报告
- Hermes cron job — 交易日定时跑脚本 + 多渠道推送（WeChat / Telegram）
- 已有 WeChat/QQ/Telegram 三通道推送能力（Hermes gateway）

**目标用户画像：** 基金讨论区 / 小红书上的散户基民，想省心盯盘，不想自己天天刷净值。

**定价：** 9.9 元/月（按月订阅）

---

## 一、产品架构总览

```
┌─────────────────────────────────────────────────┐
│                用户收到的资料包                      │
│  (GitHub 私仓 / 百度网盘 / 飞书文档)                │
├─────────────────────────────────────────────────┤
│  📦 fund-monitor-service/                        │
│  ├── docs/          ← 用户操作手册                  │
│  ├── panel/         ← 前端管理面板（静态 HTML）      │
│  ├── server/        ← 后端 API 服务（Python）        │
│  ├── hermes/        ← Hermes 配置模板               │
│  └── scripts/       ← 监控脚本 + 辅助工具            │
└─────────────────────────────────────────────────┘
```

**两种部署模式（用户二选一）：**

| 模式 | 适用人群 | 需要什么 | 我们维护什么 |
|---|---|---|---|
| **A. 自部署（Hermes 用户）** | 已有/愿意装 Hermes 的用户 | 装 Hermes + 导入配置 | 脚本 + 配置模板 |
| **B. 托管服务（SaaS）** | 小白用户 | 只注册账号 | 全套运维 |

**MVP 阶段只做模式 A**（因为代码已经有一半了），模式 B 作为付费升级方向。

---

## 二、交付物拆解

### 2.1 核心脚本改造（fund_monitor.py → fund_monitor_service.py）

**改动点：**

| 当前（个人版） | 产品化后 |
|---|---|
| `RADARS` 硬编码在脚本里 | 读取 `config/funds.json` 用户自定义列表 |
| 只支持 3 种 data_type | 统一数据源抽象层 |
| 只做涨跌幅阈值判断 | 新增：净值变更提醒、分红提醒、基金经理变更提醒 |
| 纯文本报告 | 结构化 JSON + 可选模板格式 |
| 无缓存 | 缓存上次净值，用于对比异动 |

**配置文件的格式：**

```json
{
  "user": {
    "name": "用户昵称",
    "subscribe_until": "2026-09-01",
    "channels": ["wechat", "telegram"]
  },
  "funds": [
    {
      "name": "南方科创100ETF联接C",
      "code": "019860",
      "ticker": "sh000698",
      "data_type": "index",
      "threshold": -1.5,
      "alerts": {
        "price_drop": true,
        "dividend": true,
        "manager_change": true
      }
    }
  ],
  "alerts": {
    "daily_report": true,
    "instant_alert": true,
    "quiet_hours": ["22:00-08:00"]
  }
}
```

### 2.2 前端管理面板（纯静态 HTML/JS）

**定位：** 一个 `index.html` 文件+ JS，通过后端 API 管理基金配置。不需要用户装任何东西，浏览器打开就行。

**功能：**

| 页面 | 功能 |
|---|---|
| 仪表盘 | 概览：所有基金今日净值涨跌一览 |
| 基金管理 | 增删改基金列表（搜索基金代码自动补全） |
| 告警配置 | 每只基金的阈值、告警开关 |
| 推送状态 | 查看最近推送记录、各通道状态 |
| 订阅管理 | 查看订阅到期日、续费入口 |

**技术选型：**
- 纯 HTML + Tailwind CSS（CDN）+ Vanilla JS
- 无构建步骤，打开即用
- 所有请求指向后端 API（`http://localhost:8420`）

### 2.3 后端 API 服务（Python FastAPI）

一个轻量级 API 服务，用于：
1. 管理基金配置（CRUD）
2. 提供基金搜索（基金代码补全）
3. 提供历史数据查询
4. 对接订阅验证

**API 设计：**

```
GET  /api/v1/funds           — 列出所有基金及当前净值
POST /api/v1/funds           — 添加基金
PUT  /api/v1/funds/{code}    — 修改基金配置
DELETE /api/v1/funds/{code}  — 删除基金

GET  /api/v1/search?q=南方   — 基金代码搜索
GET  /api/v1/report          — 获取最新监控报告
GET  /api/v1/alerts          — 告警历史

GET  /api/v1/subscribe       — 查询订阅状态
POST /api/v1/subscribe/verify— 验证订阅码
```

**技术栈：** Python FastAPI + SQLite + uvicorn

### 2.4 Hermes 配置模板

用户拿到资料包后，按文档操作：

```bash
# 1. 把脚本和配置复制到 Hermes 目录
cp -r fund-monitor-service/scripts/* ~/.hermes/scripts/
cp -r fund-monitor-service/config/* ~/.hermes/config/

# 2. 导入 cron job 配置
# 创建 cron job 的命令
hermes cron create \
  --name "基金监控" \
  --schedule "0 9,14 * * 1-5" \
  --script "fund_monitor_service.py" \
  --deliver "all"
```

**也提供可视化配置方式：** 用户打开面板后，点「一键部署」按钮，复制粘贴几条命令即可。

### 2.5 用户操作手册（docs/）

一份面向非技术用户的 PDF/飞书文档，内容包括：

1. **产品介绍** — 能做什么、怎么用（2 页）
2. **快速上手指南** — 10 分钟配置好（图文化）
3. **基金配置说明** — 支持的基金类型、数据源说明
4. **推送通道配置** — WeChat/QQ/Telegram 各平台怎么接
5. **常见问题** — 为什么没收到推送、数据延迟多久

---

## 三、实施计划（分 4 个 Phase）

### Phase 1: 核心脚本改造（2-3 天）

**目标：** 从个人硬编码脚本 → 可配置的通用监控服务

**任务清单：**

1. **重构数据源层**
   - 创建 `sources/` 目录，每个数据源独立模块
   - 腾讯财经模块（指数 + 基金）
   - Yahoo Finance 模块（海外指数）
   - 天天基金 API 模块（净值历史、分红、经理变更）
   - 统一接口：`fetch(ticker) -> {name, price, change_pct, ...}`

2. **新增数据源：天天基金 API**
   - 基金净值历史查询
   - 分红公告抓取
   - 基金经理变更检测
   - 参考：`fundf10.eastmoney.com` 接口

3. **新增异动检测逻辑**
   - 涨跌幅阈值（已有）
   - 净值日变更（涨/跌超过 X%）
   - 分红/拆分公告
   - 基金经理变更
   - 基金规模/持仓显著变化

4. **配置系统**
   - `config/funds.json` 配置文件
   - `config/user.json` 用户配置
   - 配置校验 + 默认值

5. **缓存系统**
   - SQLite 或 JSON 文件缓存上次净值
   - 用于对比「上次 vs 本次」的异动

### Phase 2: 后端 API + 前端面板（3-4 天）

**目标：** 用户能通过浏览器管理基金配置

**任务清单：**

1. **FastAPI 后端**
   - 项目骨架：`server/main.py`, `server/models.py`, `server/routes/`
   - SQLite 数据库：funds 表、alerts 表、subscribe 表
   - CRUD API：基金增删改查
   - 基金搜索 API（对接天天基金代码库）
   - 订阅验证 API（验证订阅码）

2. **前端管理面板**
   - 仪表盘页面（净值概览卡片）
   - 基金列表管理（添加/删除/编辑）
   - 基金搜索组件（输入代码自动补全）
   - 告警配置表单
   - 推送历史记录

3. **前后端联调**
   - 后端提供 `npm run dev` 等价的一键启动
   - 前端面板通过 `index.html` 加载

### Phase 3: 打包交付物（1-2 天）

**目标：** 用户拿到资料包后，按文档 10 分钟跑起来

**任务清单：**

1. **目录结构标准化**
   ```
   fund-monitor-service/
   ├── README.md
   ├── start.sh / start.bat       # 一键启动
   ├── docs/
   │   ├── 01-产品介绍.md
   │   ├── 02-快速上手.md
   │   ├── 03-基金配置说明.md
   │   ├── 04-推送通道配置.md
   │   └── 05-常见问题.md
   ├── server/
   │   ├── main.py
   │   ├── models.py
   │   ├── routes/
   │   │   ├── funds.py
   │   │   ├── alerts.py
   │   │   └── subscribe.py
   │   └── requirements.txt
   ├── panel/
   │   ├── index.html
   │   ├── dashboard.html
   │   ├── funds.html
   │   ├── alerts.html
   │   └── assets/
   │       ├── app.js
   │       └── style.css
   ├── hermes/
   │   ├── config-template.yaml   # Hermes 配置模板
   │   ├── cron-import.sh         # 一键导入 cron job
   │   └── setup-guide.md
   ├── scripts/
   │   ├── fund_monitor_service.py
   │   ├── sources/
   │   │   ├── __init__.py
   │   │   ├── tencent.py
   │   │   ├── yahoo.py
   │   │   └── eastmoney.py
   │   ├── detectors/
   │   │   ├── __init__.py
   │   │   ├── price.py
   │   │   ├── dividend.py
   │   │   └── manager.py
   │   └── utils/
   │       ├── cache.py
   │       ├── config.py
   │       └── notify.py
   └── config/
       ├── funds.json.example
       └── user.json.example
   ```

2. **一键启动脚本**
   - Windows: `start.bat` — 启动后端 + 打开浏览器
   - 检测 Python 环境，自动安装依赖

3. **用户手册编写**
   - 图文并茂，非技术用户能看懂
   - 包括：截图、操作步骤、预期效果

### Phase 4: 分发 + 商业化（持续）

**目标：** 用户能付费订阅，我们能持续收钱

**任务清单：**

1. **订阅验证系统**
   - 生成订阅码（HMAC 签名）
   - 本地验证或联网验证
   - 到期提醒

2. **分发渠道**
   - 基金讨论区（天天基金、蚂蚁财富）
   - 小红书（图文种草）
   - 知乎/公众号（理财工具推荐）
   - 淘宝/闲鱼（9.9 元链接）

3. **引流策略**
   - 免费版：支持 3 只基金监控
   - 付费版：不限基金数量 + 异动提醒 + 历史回测
   - 分享裂变：推荐 1 人送 1 个月

4. **后续迭代方向**
   - 模式 B：SaaS 托管服务（用户不用装 Hermes）
   - 移动端：微信小程序 / 公众号菜单
   - 数据增值：净值趋势图、组合分析

---

## 四、技术选型 & 关键决策

### 数据源

| 数据源 | 用途 | 稳定性 |
|---|---|---|
| 腾讯财经 `web.sqt.gtimg.cn` | 实时指数/基金估值 | ⭐⭐⭐⭐ |
| Yahoo Finance | 海外指数（标普500等） | ⭐⭐⭐（需代理） |
| 天天基金 `fund.eastmoney.com` | 净值历史、分红、经理变更 | ⭐⭐⭐⭐⭐ |
| 东方财富 | 备选数据源 | ⭐⭐⭐⭐ |

### 推送通道

| 通道 | 成本 | 用户覆盖 | Hermes 支持 |
|---|---|---|---|
| WeChat（iLink/企业微信） | 免费 | 最广 | ✅ 已有 |
| QQ（NapCat/SnowLuma） | 免费 | 广 | ✅ 已有 |
| Telegram | 免费 | 中 | ✅ 已有 |
| 邮件（SMTP） | 免费 | 广 | 需新增 |
| 短信（备用） | 付费 | 广 | 不推荐 |

### 关键决策

1. **MVP 只做模式 A（自部署）**，用户需要装 Hermes 或用 Python 直接跑
2. **配置优先 YAML/JSON**，不要数据库依赖，用户改文件就能用
3. **前端面板是可选增强**，核心功能命令行也能操作
4. **订阅验证 MVP 阶段用本地 HMAC 码**，后续再上联网验证
5. **用户隐私：基金代码不包含个人身份信息**，不上传服务器

---

## 五、风险 & 边界

### 风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 数据源接口变更 | 中 | 高 | 多数据源冗余 + 切换机制 |
| 推送通道被封 | 低 | 中 | 多渠道推送，一条挂了走另一条 |
| 用户不会配 Hermes | 高 | 高 | 提供 docker 方案 / 纯 Python 模式 |
| 基金数据延迟 | 中 | 低 | 标注数据延迟时间，管理预期 |
| 合规风险 | 低 | 高 | 不做投资建议，只做数据展示 |

### 不做（MVP 阶段）

- ❌ 用户管理系统（多用户隔离）
- ❌ 支付系统对接（人工收款验证）
- ❌ 移动端 App
- ❌ 量化交易信号
- ❌ 社区/论坛功能

---

## 六、MVP 验证清单

开卖前需要确认以下全部完成：

- [ ] `fund_monitor_service.py` 支持自定义基金列表（通过 `funds.json`）
- [ ] 至少有 3 个数据源覆盖 A 股基金 + 海外指数
- [ ] 涨跌幅阈值告警 ✅
- [ ] 净值日变更告警
- [ ] 分红公告检测
- [ ] 基金经理变更检测
- [ ] 后端 API 可运行（`python server/main.py`）
- [ ] 前端面板可打开、可编辑基金列表
- [ ] 用户手册写完（含截图）
- [ ] 一键启动脚本（Windows `start.bat`）
- [ ] 已在小红书/基金讨论区发 1 篇引流帖
- [ ] 已有 1 个付费用户

---

## 七、实施顺序建议

```
Week 1: Phase 1 — 核心脚本改造（已有 50% 代码）
Week 2: Phase 2 — 后端 API + 前端面板
Week 3: Phase 3 — 打包 + 写文档
Week 4: Phase 4 — 分发 + 收第一个付费用户
```

**先做最核心的：** 脚本支持自定义基金列表 → 写文档 → 发给第一个潜在用户收反馈 → 再写前端。

---

## 八、立即可以做的事

基于现有代码，**今天就能开始**：

1. 把 `fund_monitor.py` 的 `RADARS` 硬编码改成读取 `funds.json`
2. 添加天天基金净值历史 API（用于分红检测）
3. 写一份「产品介绍 + 使用说明」的 Notion/飞书文档
4. 在小红书发第一篇「基金自动盯盘工具」的种草文

---

*Plan by Hermes Agent | 2026-08-05*