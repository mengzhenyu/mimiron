# 观星系统 E2E 自动化测试

基于 **Python + Playwright + pytest + Allure** 的端到端自动化测试项目，覆盖观星系统（Stargazer）的登录功能与工作台菜单页面。

## 技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| Python | 3.x | 运行时 |
| Playwright | latest | 浏览器自动化引擎 |
| pytest | 8.1.1 | 测试框架 |
| allure-pytest | 2.13.2 | 测试报告生成 |
| requests | 2.31.0 | HTTP 接口测试 |

## 项目结构

```
mimiron/
├── tests/                      # 测试用例
│   ├── test_login.py           # 登录功能测试 (4 个用例)
│   ├── test_gongzuotai.py      # 工作台菜单页面测试 (30 个用例)
│   └── test_example.py         # 示例用例 (HTTP 接口测试)
├── conftest.py                 # pytest 全局配置 + 失败用例自动截图
├── requirements.txt            # Python 依赖
├── run_and_report.sh           # 一键运行 + 启动 Allure 报告
├── 常用命令                     # 常用命令速查手册
├── .gitignore                  # 忽略规则
└── venv/                       # 虚拟环境 (不入库)
```

## 被测系统

- **系统名称**：观星系统（Stargazer）
- **测试环境地址**：`https://stargazer-test.mimiron.cn:8443`
- **登录页地址**：`https://stargazer-test.mimiron.cn:8443/login`

## 环境准备

### 1. 安装依赖

```bash
pip install -r requirements.txt
pip install playwright allure-pytest
playwright install chromium
```

### 2. 配置环境变量

运行测试前必须设置以下环境变量（密码不写入代码）：

```bash
# 登录密码 (必填)
export LOGIN_PASSWORD='your_password_here'

# 无头模式 (调试时设 false, CI 时设 true, 默认 true)
export HEADLESS=false

# 可选: 覆盖默认配置
# export LOGIN_USERNAME='zhenyu_m'
# export GONGZUOTAI_BASE_URL='https://stargazer-test.mimiron.cn:8443'
# export GONGZUOTAI_LOGIN_URL='https://stargazer-test.mimiron.cn:8443/login'
```

## 运行测试

### 一键运行 + 查看报告

```bash
bash run_and_report.sh
```

该脚本会自动运行 `test_gongzuotai.py` 并在 `http://127.0.0.1:59882` 启动 Allure 报告。

### 常用命令

```bash
# 运行全部用例
venv/bin/python -m pytest tests/ --alluredir=./allure-results --clean-alluredir

# 仅运行工作台测试 (30 个用例)
venv/bin/python -m pytest tests/test_gongzuotai.py -v --alluredir=./allure-results --clean-alluredir

# 运行单个用例
venv/bin/python -m pytest tests/test_gongzuotai.py::TestGongZuoTai::test_tab_switch_between_three_tabs -v --alluredir=./allure-results

# 按关键词筛选运行
venv/bin/python -m pytest tests/test_gongzuotai.py -v -k "search" --alluredir=./allure-results

# 仅运行上次失败的用例
venv/bin/python -m pytest tests/test_gongzuotai.py -v --lf --alluredir=./allure-results

# 运行并打印详细日志
venv/bin/python -m pytest tests/test_gongzuotai.py -v -s --alluredir=./allure-results
```

> 无需先激活虚拟环境，所有命令统一使用 `venv/bin/python -m pytest` 形式直接运行。

## 查看报告

```bash
# 生成临时报告并启动 web 服务 (指定端口)
allure serve ./allure-results --port 59882

# 生成静态报告到目录
allure generate ./allure-results -o ./allure-report --clean

# 用默认浏览器打开静态报告
open allure-report/index.html
```

## 测试用例概览

共 **35 个用例**，分布如下：

### 登录功能 (`test_login.py` - 4 个用例)

| 用例 | 说明 |
|------|------|
| 正常账号密码登录 | 验证登录成功后跳转首页并显示用户姓名 |
| 错误密码登录 | 验证错误密码提示"用户名/密码不正确" |
| 空用户名提交 | 验证空用户名表单校验提示 |
| 空密码提交 | 验证空密码表单校验提示 |

### 工作台菜单 (`test_gongzuotai.py` - 30 个用例)

覆盖工作台 3 个 Tab（工作台 / 待办中心 / 测点视图）的以下维度：

- **Tab 切换**：三 Tab 互切、快速连续切换、重复点击已选中 Tab
- **元素可见性**：各 Tab 核心组件（搜索框、日历、表格、分页、树形控件）渲染验证
- **快捷入口导航**：告警盯屏 / 考试管理 / 事件列表 / 变更列表 / 风险登记册 / 维护工单 / 上下电工单 / 巡检工单
- **搜索功能**：正常搜索、无结果搜索、清空恢复、特殊字符（XSS/SQL 注入字符）安全输入
- **测点视图**：设备树查询、条件重置、空条件查询
- **待办中心**：状态标签切换、重复点击状态保持
- **审批中心**：待办/已办/我发起的/抄送我的 4 个子页导航 + 单选切换
- **运维工单**：卡片可见性 + 事件列表导航
- **日历视图**：年视图 ↔ 月视图切换

### 示例用例 (`test_example.py` - 1 个用例)

HTTP 接口状态码验证，用于验证 allure 报告框架集成。

## 设计规范

| 规范 | 说明 |
|------|------|
| 凭据隔离 | 账号密码通过环境变量注入，禁止硬编码 |
| 语义定位 | 优先 `get_by_role` / `get_by_text` / `get_by_placeholder`，不使用绝对 XPath |
| 自动等待 | 统一使用 `expect` 断言，禁止 `time.sleep` |
| 用例隔离 | 每个用例独立浏览器上下文（function 级），互不影响 |
| 报告标记 | 全部用例使用 `@allure.feature` / `@allure.story` 装饰器分类 |
| 失败截图 | `conftest.py` 自动在用例失败时截取全页面快照并记录错误堆栈到 Allure 报告 |

## 目录说明

| 目录 | 是否入库 | 说明 |
|------|----------|------|
| `tests/` | ✅ | 测试用例源码 |
| `conftest.py` | ✅ | pytest 全局配置与 hook |
| `allure-results/` | ❌ | Allure 测试结果（运行时生成） |
| `allure-report/` | ✅ | Allure 静态报告（运行时生成） |
| `venv/` | ❌ | Python 虚拟环境 |
| `.pytest_cache/` | ❌ | pytest 缓存 |
| `__pycache__/` | ❌ | Python 字节码缓存 |
