# FRP 统一管理平台

一套面向内网穿透运维场景的 FRP 集中管理平台。后端基于 Django REST Framework，
前端基于 Vue 3 + Vite + TypeScript，用于统一纳管 frps 服务端、frpc 客户端与端口隧道，
并提供准入审核、运行态同步、流量统计与全量操作审计。

- 默认访问地址：http://127.0.0.1:5173
- 默认账号：`admin` / `admin123`（仅限本地开发，生产环境请立即修改）

## 界面预览

登录页：

![登录页](docs/images/01-login.png)

FRP 服务端与 frpc 客户端：

![FRP 服务端](docs/images/02-frp-servers.png)

![frpc 客户端](docs/images/03-frp-agents.png)

FRP 隧道配置与连接审计：

![FRP 隧道](docs/images/04-frp-proxies.png)

![FRP 审计](docs/images/05-frp-audits.png)

FRP 报表中心与流量报表：

![FRP 报表](docs/images/06-frp-reports.png)

![流量报表](docs/images/07-frp-traffic.png)

---

## 一、开发环境与版本

### 1.1 基础环境

| 项目 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.12（实测 3.12.10） | 后端运行时 |
| Node.js | ≥ 22（实测 v24.13.0） | 前端开发服务器与构建 |
| npm | ≥ 10（实测 11.6.2） | 前端包管理 |
| Django | 4.2 LTS | Web 框架 |
| 数据库 | SQLite 3 | 默认内置，开箱即用 |
| frp | 建议 v0.52.0+ | 被纳管的 frps / frpc |
| 浏览器 | Chrome / Edge 最新版 | 前端为 SPA 应用 |

### 1.2 后端依赖（`backend/requirements.txt`）

```
Django>=4.2,<5.0
django-cors-headers>=4.9,<5.0
djangorestframework>=3.17,<4.0
gmssl>=3.2.2,<4.0
openpyxl>=3.1,<4.0
psutil>=7.0,<8.0
PyJWT>=2.12,<3.0
requests>=2.33,<3.0
icmplib>=3.0,<4.0
```

### 1.3 前端依赖（`front/package.json`）

运行依赖：

- `vue` ^3.5.34、`vue-router` ^4.6.4、`pinia` ^3.0.4
- `echarts` ^6.1.0 — 报表图表渲染
- `html2canvas` ^1.4.1、`jspdf` ^4.2.1 — 报表导出
- `@vuepic/vue-datepicker` ^14.0.0、`date-fns` ^4.4.0 — 日期选择
- `lucide-vue-next` ^0.577.0 — 图标库
- `qrcode` ^1.5.4 — 二维码（OTP 绑定）

开发依赖：

- `vite` ^7.3.1、`@vitejs/plugin-vue` ^6.0.7
- `typescript` ^5.9.2、`vue-tsc` ^3.3.2
- `tailwindcss` ^4.1.13、`@tailwindcss/postcss` ^4.1.13、`postcss` ^8.5.6

---

## 二、技术架构

### 2.1 技术栈

| 层次 | 技术选型 |
| --- | --- |
| 后端框架 | Django 4.2 + Django REST Framework 3.17 |
| 数据库 | SQLite 3（通过 Django ORM 访问） |
| 身份认证 | JWT（PyJWT）+ 图形验证码 + 滑块验证，可选 OTP 二次验证 |
| 前端框架 | Vue 3 + TypeScript + Vite 7 |
| 状态管理 | Pinia |
| UI 样式 | Tailwind CSS 4 |
| 图表 / 导出 | ECharts 6、html2canvas、jsPDF |
| 加解密 | gmssl（国密 SM4，用于敏感配置落库加密） |
| 运维探测 | icmplib / psutil / requests（ping、telnet、curl、traceroute、mtr） |

### 2.2 目录结构

```
frpsys/
├── backend/                 # Django 后端
│   ├── backend/             # 项目配置：settings / urls / asgi / wsgi
│   ├── ops/                 # 平台基础能力：用户、组织、角色、权限、系统设置与系统工具
│   ├── identity/            # 身份认证相关实现（验证码、OTP、密码策略等）
│   ├── security_frp/        # FRP 管理核心模块：服务端、客户端、隧道、心跳、审计、报表
│   ├── data_security/       # 数据安全与国密加解密能力
│   ├── platform_logs/       # 用户操作日志与系统日志
│   ├── scripts/             # 运维脚本
│   ├── requirements.txt     # 后端依赖清单
│   └── manage.py            # Django 管理入口
├── front/                   # Vue 3 前端
│   ├── src/                 # 源码：views / components / stores / utils / styles
│   ├── package.json         # 前端依赖与脚本
│   └── vite.config.ts       # Vite 配置（含开发代理）
└── docs/images/             # README 截图资源
```

---

## 三、快速开始

### 3.1 启动后端

```bash
cd backend

# 1. 创建并激活虚拟环境（可选但推荐）
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

# 2. 安装依赖
pip install -r requirements.txt

# 3. 初始化数据库
python manage.py migrate

# 4. 创建默认管理员 admin / admin123
python manage.py seed_demo

# 5. 启动服务，端口需与前端代理保持一致（默认 8001）
python manage.py runserver 0.0.0.0:8001
```

### 3.2 启动前端

```bash
cd front

# 1. 安装依赖
npm install

# 2. 启动开发服务器（默认 http://127.0.0.1:5173）
npm run dev
```

### 3.3 生产构建

```bash
cd front
npm run build      # 依次执行资源审计、文档审计、类型检查，产物输出到 front/dist
```

后端 `settings.py` 中的 `FRONT_DIST_DIR` 指向 `front/dist`，
关闭 `DEBUG` 后可由 Django 直接托管；也可用 Nginx 托管 `front/dist` 并将 `/api` 反向代理到后端端口。

### 3.4 登录

浏览器打开 http://127.0.0.1:5173，使用 `admin` / `admin123` 登录。
登录页默认启用图形验证码与滑块验证；OTP 二次验证、短信登录可在「系统设置 → 平台安全」中开关。
