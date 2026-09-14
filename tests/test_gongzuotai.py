# -*- coding: utf-8 -*-
"""
观星系统 - Web 工作台菜单页面 E2E 自动化测试
================================================================
技术栈: Python + Playwright + pytest + allure
被测地址: https://stargazer-test.mimiron.cn:8443/login

页面说明:
  左侧全局侧边导航菜单 -> 工作台, 包含 3 个 Tab:
    1. 工作台 (默认) - 项目名称栏 / 常用导航区(搜索框+快捷按钮) / 运维行事历日历
    2. 待办中心     - 待办分类树 / 状态标签 / 审批列表表格 / 分页
    3. 测点视图     - 三栏布局: 空间树 / 设备类型树 / 查询表单+测点表格+分页

  工作台常用导航区快捷入口:
    告警盯屏 / 考试管理 / 事件列表 / 变更列表 / 风险登记册
    维护工单 / 上下电工单 / 巡检工单

设计要点:
  1. 账号密码 / 被测 URL 通过环境变量注入, 禁止硬编码;
  2. 登录元素定位预留注释, 由使用者自行补全;
  3. 定位优先 get_by_role / get_by_text / get_by_placeholder, 不使用绝对 XPath;
  4. 禁止 time.sleep, 统一使用 expect 断言;
  5. 每个用例独立浏览器上下文 (function 级), 互不影响;
  6. 全部用例加 @allure.feature / @allure.story 装饰器.
================================================================
"""

import os
import re

import pytest
import allure
from playwright.sync_api import sync_playwright, expect, Page


# ==================== 测试配置 (环境变量注入, 避免硬编码) ====================

# 被测系统基础地址
BASE_URL = os.getenv("GONGZUOTAI_BASE_URL", "https://stargazer-test.mimiron.cn:8443")

# 登录页地址
LOGIN_URL = os.getenv("GONGZUOTAI_LOGIN_URL", "https://stargazer-test.mimiron.cn:8443/login")

# 登录账号: 用户名非敏感, 设默认值; 密码必须通过环境变量提供 (不写入代码)
LOGIN_USERNAME = os.getenv("LOGIN_USERNAME", "zhenyu_m")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "")  # 运行前: export LOGIN_PASSWORD='xxx'

# 是否无头模式运行
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"


# ==================== 元素定位器 (集中管理, 便于维护) ====================
# 说明: 工作台基于 Ant Design, 以下定位优先使用语义角色 / 文本 / id,
#       具体选择器以实际 DOM 为准, 必要时按注释提示调整.

# ---------- Tab 定位 (Ant Design Tabs, role=tab) ----------

def tab_workbench(page: Page):
    """工作台 Tab"""
    return page.get_by_role("tab", name="工作台")


def tab_todo_center(page: Page):
    """待办中心 Tab"""
    return page.get_by_role("tab", name="待办中心")


def tab_point_view(page: Page):
    """测点视图 Tab"""
    return page.get_by_role("tab", name="测点视图")


def switch_to_tab(tab_locator, max_retries: int = 3):
    """
    切换到指定 Tab 并校验其选中状态 (Ant Design 选中 Tab 含 aria-selected=true).
    SPA 页面切换时 DOM 可能被重新挂载 (detached), 导致 click 失效或 aria-selected 未更新.
    采用重试机制: 每次先等待元素可见, 点击后等待 aria-selected=true, 失败则重试.
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            tab_locator.wait_for(state="visible", timeout=10000)
            tab_locator.click()
            expect(tab_locator).to_have_attribute("aria-selected", "true", timeout=10000)
            return
        except Exception as e:
            last_error = e
            continue
    raise last_error


# ---------- 工作台 Tab 元素 ----------

def workbench_search_input(page: Page):
    """常用导航区 - 搜索框 (按 placeholder 模糊匹配)"""
    return page.get_by_placeholder(re.compile(r"搜索|请输入"))


def calendar_container(page: Page):
    """运维行事历日历组件 (Ant Design Calendar)"""
    return page.locator(".ant-picker-calendar").first


def calendar_legend(page: Page):
    """
    日历 - 图例 (实测无独立"图例"标题, 图例项为 ant-badge-status-text 色块文本).
    图例项: 待执行 / 已触发 / 已取消 / 已延期 / 失败 (位于日历组件外层).
    """
    return page.locator(".ant-badge-status-text", has_text="待执行").first


def calendar_year_month_select(page: Page):
    """
    日历 - 年月下拉选择器 (Ant Design Select).
    实测年月下拉不在 .ant-picker-calendar 容器内, 而是页面级 2 个 role=combobox
    (y≈522 处, 第一个含"2026"年, 第二个为月). 这里返回第一个 (年下拉).
    """
    return page.get_by_role("combobox").nth(0)


def calendar_month_view_button(page: Page):
    """
    日历 - 月视图切换.
    实测非 Ant Design Segmented, 而是 ant-radio-button-wrapper (Radio.Group 按钮模式),
    且位于日历容器外层 (y≈528). 选中态通过 ant-radio-button-wrapper-checked 类标记.
    """
    return page.locator(".ant-radio-button-wrapper", has_text="月")


def calendar_year_view_button(page: Page):
    """
    日历 - 年视图切换.
    实测非 Ant Design Segmented, 而是 ant-radio-button-wrapper (Radio.Group 按钮模式),
    且位于日历容器外层 (y≈528). 选中态通过 ant-radio-button-wrapper-checked 类标记.
    """
    return page.locator(".ant-radio-button-wrapper", has_text="年")


def calendar_date_cells(page: Page):
    """日历 - 日期格子"""
    return calendar_container(page).locator(".ant-picker-cell")


# ---------- 工作台常用导航区 (快捷入口) ----------

def quick_nav_item(page: Page, name: str):
    """
    工作台常用导航区 - 快捷功能入口.
    实测为 ant-space 布局中的可点击文本元素 (非 link/button, 但可点击导航).
    名称: 告警盯屏 / 考试管理 / 事件列表 / 变更列表 / 风险登记册
          维护工单 / 上下电工单 / 巡检工单
    """
    return page.get_by_text(name, exact=True)


def sidebar_workbench_link(page: Page):
    """
    左侧全局侧边导航菜单 - '工作台'链接 (用于从子页面返回工作台).
    实测为 <a> 标签, href=/dashboard, 位于菜单最顶部.
    """
    return page.get_by_role("link", name="工作台").first


def navigate_back_to_workbench(page: Page):
    """
    页面返回操作, 重新返回至工作台菜单栏, 工作台 Tab.
    单次登录模式下用例间共享 page, 为保证状态干净, 统一直接导航至 /dashboard.
    校验: URL 回到 /dashboard 且工作台 Tab 处于选中状态.
    """
    page.goto(BASE_URL + "/dashboard", wait_until="networkidle")
    expect(page).to_have_url(re.compile(r"/dashboard"), timeout=15000)
    expect(tab_workbench(page)).to_have_attribute("aria-selected", "true", timeout=10000)


# ---------- 通用列表页元素 (事件/变更/风险 等) ----------

def list_page_table_header(page: Page):
    """列表页 - 表格表头 (Ant Design Table thead)"""
    return page.locator(".ant-table-thead").first


def list_page_pagination(page: Page):
    """列表页 - 分页控件 (Ant Design Pagination)"""
    return page.locator(".ant-pagination").first


def list_page_query_button(page: Page):
    """列表页 - 查询按钮 (Ant Design 两字按钮中间插空格: "查 询")"""
    return page.get_by_role("button", name=re.compile(r"查\s*询"))


def list_page_reset_button(page: Page):
    """列表页 - 重置按钮 (Ant Design 两字按钮中间插空格: "重 置")"""
    return page.get_by_role("button", name=re.compile(r"重\s*置"))


def list_page_expand_link(page: Page):
    """
    列表页 - 展开链接 (查询表单高级搜索展开/收起).
    实测为 <a> 标签, 文本"展开"/"收起", 位于查询表单右侧.
    """
    return page.get_by_text("展开", exact=True)


def list_page_export_button(page: Page):
    """列表页 - 导出按钮"""
    return page.get_by_role("button", name="导出")


def list_page_create_button(page: Page, name: str):
    """列表页 - 创建XX按钮 (如 创建事件 / 创建变更 / 创建风险)"""
    return page.get_by_role("button", name=re.compile(name))


# ---------- 告警盯屏页面元素 ----------

def alarm_screen_tab(page: Page, name: str):
    """告警盯屏页面 - Tab (状态看板 / 级别看板 / 分析 / AI 看板 / 列表)"""
    return page.get_by_role("tab", name=name)


# ---------- 考试管理页面元素 ----------

def exam_category_tree(page: Page):
    """考试管理 - 左侧考试分类结构树 (Ant Design Tree)"""
    return page.locator(".ant-tree").first


def exam_form_label(page: Page, label_text: str):
    """考试管理 - 查询表单标签 (通过 ant-form-item-label 定位)"""
    return page.locator(".ant-form-item-label", has_text=label_text).first


# ---------- 工单页面元素 (维护/上下电/巡检) ----------
# 实测在 1800x1300 viewport 下, 工单页面渲染为标准表格布局 (非卡片),
# 含: 查询表单 (重置/查询/展开) + 表格 (工单编号/工单标题/工单子类型/创建时间/进度/操作) + 分页

def workorder_table_header(page: Page):
    """工单页面 - 表格表头"""
    return page.locator(".ant-table-thead").first


def workorder_pagination(page: Page):
    """工单页面 - 分页控件"""
    return page.locator(".ant-pagination").first


# ---------- 待办中心 Tab 元素 ----------

def todo_category_tree(page: Page):
    """
    左侧待办分类树 (实测为 Ant Design Menu, 非 Tree).
    含两个分组: 工单 (待处理 / 待接单) + 审批 (待我审批 / 我已处理 / 我创建的 / 抄送我的).
    """
    return page.locator(".ant-menu").last


def todo_status_tab(page: Page, name: str):
    """
    顶部状态标签 (全部 / 审批中 / 审批通过 / 审批拒绝).
    实测为 Ant Design Radio.Group (ant-radio-button-wrapper), 非 Tabs.
    选中态通过父元素的 ant-radio-button-wrapper-checked 类标记.
    """
    return page.locator(".ant-radio-button-wrapper", has_text=name)


def todo_table(page: Page):
    """审批列表表格"""
    return page.locator(".ant-table").first


def todo_table_header(page: Page):
    """审批列表表头"""
    return todo_table(page).locator("thead").first


def todo_view_button(page: Page):
    """审批列表 - 操作列【查看】按钮 (每行一个, 取第一个; 兼容 Ant Design 两字按钮空格)"""
    return page.get_by_role("button", name=re.compile(r"查\s*看")).first


def todo_pagination(page: Page):
    """待办中心 - 分页控件"""
    return page.locator(".ant-pagination").first


# ---------- 测点视图 Tab 元素 ----------
# 实测测点视图为 ant-splitter-panel 三栏布局: 空间树 | (设备类型树面板, 宽度0已折叠) | 右栏.
# 右栏含 ant-segmented 控件 ("测点"/"设备" 两项, 选中态通过 class 含 selected 标记),
# 内容区 (ant-empty 暂无数据 或数据列表) + 分页控件 (有数据时显示).
# 空间树含搜索框 (placeholder="支持检索：标题关键字、工单类型").

def space_tree(page: Page):
    """左栏 - 空间树"""
    return page.locator(".ant-tree").first


def space_tree_node(page: Page, node_name: str):
    """左栏 - 空间树指定节点 (按文本模糊匹配, 节点文本含数量统计如 "1号楼 (8)")"""
    return space_tree(page).get_by_text(node_name, exact=False).first


def point_segmented_item(page: Page, name: str):
    """
    右栏 - "测点"/"设备" 切换控件 (ant-segmented-item).
    选中态通过 class 含 "ant-segmented-item-selected" 标记 (无 aria-selected).
    """
    return page.locator(".ant-segmented-item", has_text=name).first


def point_empty(page: Page):
    """右栏 - 暂无数据占位 (ant-empty)"""
    return page.locator(".ant-empty").first


def point_pagination(page: Page):
    """右栏 - 分页控件 (有数据时显示, 暂无数据时不显示)"""
    return page.locator(".ant-pagination").first


# ---------- 测点视图 - 设备页元素 (点击'设备'后显示) ----------
# 实测点击'设备'后右栏展示: 设备类型树 (第2棵 ant-tree) + 查询表单
# (GUID输入框 id=guid / 设备名称输入框 id=name / 启用状态复选框 / 重置 / 查询)
# + 数据表格 (GUID/设备名称/设备房间/设备类型/厂商/型号/启用状态) + 分页.

def device_type_tree(page: Page):
    """设备页 - 设备类型树 (切换到'设备'后出现的第2棵 ant-tree)"""
    return page.locator(".ant-tree").nth(1)


def device_guid_input(page: Page):
    """设备页 - GUID 输入框 (input id=guid, placeholder='请输入')"""
    return page.locator("#guid")


def device_name_input(page: Page):
    """设备页 - 设备名称输入框 (input id=name, placeholder='请输入')"""
    return page.locator("#name")


def device_query_button(page: Page):
    """设备页 - 查询按钮 (两字按钮含空格: '查 询')"""
    return page.get_by_role("button", name=re.compile(r"查\s*询"))


def device_reset_button(page: Page):
    """设备页 - 重置按钮 (两字按钮含空格: '重 置')"""
    return page.get_by_role("button", name=re.compile(r"重\s*置"))


def device_table_header(page: Page):
    """设备页 - 表格表头"""
    return page.locator(".ant-table-thead").first


def device_pagination(page: Page):
    """设备页 - 分页控件"""
    return page.locator(".ant-pagination").first


# ---------- 审批中心元素 (工作台 Tab 内) ----------
# 实测审批中心位于工作台 Tab 下方, 含 4 个统计卡片 (ant-statistic),
# 每个卡片含标签 (待我审批/我已处理/我发起的/我收到的) + 数字链接 (a[href*='/todo-center/']).
# 点击数字链接后页面不跳转 URL, 但内容切换为待办中心审批列表 (含 Radio.Group + 查询表单 + 表格).

def approval_center_card(page: Page, card_label: str):
    """
    审批中心 - 单个统计卡片 (按标签文本定位).
    card_label: '待我审批' / '我已处理' / '我发起的' / '我收到的'.
    """
    return page.locator(".ant-statistic", has=page.locator(".ant-statistic-title", has_text=card_label)).first


def approval_center_number_link(page: Page, card_label: str):
    """
    审批中心 - 卡片下方的数字链接 (a[href*='/todo-center/']).
    card_label 用于定位所属卡片, 返回卡片内的 <a> 链接.
    """
    return approval_center_card(page, card_label).locator("a").first


def approval_radio_tab(page: Page, tab_name: str):
    """
    跳转后页面 - 审批 Radio.Group 子 Tab (含括号数字).
    tab_name: '待我审批' / '我已处理' / '我创建的' / '抄送我的'.
    选中态通过 ant-radio-button-wrapper-checked 类标记.
    """
    return page.locator(".ant-radio-button-wrapper", has_text=tab_name).first


def approval_form_label(page: Page, label_text: str):
    """跳转后页面 - 查询表单标签 (审批ID / 审批标题 / 审批类型 / 状态)"""
    return page.locator(".ant-form-item-label", has_text=label_text).first


def approval_form_input(page: Page):
    """跳转后页面 - 查询表单输入框 (placeholder='请输入', 取第一个)"""
    return page.get_by_placeholder("请输入").first


def approval_reset_button(page: Page):
    """跳转后页面 - 重置按钮 (两字按钮含空格: '重 置')"""
    return page.get_by_role("button", name=re.compile(r"重\s*置"))


def approval_query_button(page: Page):
    """跳转后页面 - 查询按钮 (两字按钮含空格: '查 询')"""
    return page.get_by_role("button", name=re.compile(r"查\s*询"))


def approval_collapse_link(page: Page):
    """跳转后页面 - 收起链接 (a 标签, 查询表单右侧)"""
    return page.locator("a", has_text="收起").first


def approval_table_header(page: Page):
    """跳转后页面 - 审批列表表头"""
    return page.locator(".ant-table-thead").first


def approval_pagination(page: Page):
    """跳转后页面 - 分页控件"""
    return page.locator(".ant-pagination").first


# ---------- 运维工单元素 (工作台 Tab 内) ----------
# 实测运维工单位于审批中心下方, 与审批中心同为 ant-statistic 卡片结构 (共 8 个):
# 事件管理(a->/event) / 变更管理(a->/change) / 风险管理(a->/risk) / 演练管理(a->/dashboard/search)
# 上下电管理(a->/task/power) / 维护管理(a->/task/maintain) / 维修管理(a->/task/repair) / 待下发工单(a->/task/dispatch)
# 卡片数字异步加载, 初始渲染为 "0", 加载完成后显示真实统计值.

def om_card(page: Page, card_label: str):
    """
    运维工单 - 单个统计卡片 (按标签文本定位, 与审批中心同为 ant-statistic 结构).
    card_label: '事件管理' / '变更管理' / '风险管理' / '演练管理'
                '上下电管理' / '维护管理' / '维修管理' / '待下发工单'.
    """
    return approval_center_card(page, card_label)


def om_number_link(page: Page, card_label: str):
    """运维工单 - 卡片下方的数字链接 (<a> 标签, 点击跳转对应菜单页)"""
    return approval_center_number_link(page, card_label)


# ---------- 事件列表页元素 (展开/收起 查询表单 + 横向滚动表格) ----------
# 实测事件列表页 (/event) 查询表单收起时仅展示 3 项: 事件名称 / 事件类型 / 事件等级;
# 点击"展开"后追加显示: 事件ID / 事件来源 / 事件状态 / 楼栋 / 机柜影响 / 责任人 / 创建人
#                      / 设备类型 / 故障设备 / 房间类型 / 故障房间 / 创建时间 / 事件识别时间 / 关闭时间.
# 表格为固定表头 + 横向滚动结构, 滚动容器为 .ant-table-body (表头随滚动同步).

def event_form_label(page: Page, label_text: str):
    """事件列表 - 查询表单标签 (通过 ant-form-item-label 定位)"""
    return page.locator(".ant-form-item-label", has_text=label_text).first


def event_collapse_link(page: Page):
    """事件列表 - 收起链接 (查询表单展开后显示, <a> 标签)"""
    return page.locator("a", has_text="收起").first


def event_table_body(page: Page):
    """事件列表 - 表格横向滚动容器 (ant-table-body, scrollWidth > clientWidth)"""
    return page.locator(".ant-table-body").first


def event_table_header(page: Page):
    """事件列表 - 表格表头 (thead, 含全部 25 列, 横向滚动由 ant-table-body 驱动同步)"""
    return page.locator(".ant-table-thead").first


def workbench_menu_item(page: Page):
    """左侧全局导航菜单 - 工作台菜单项 (role=menuitem)"""
    return page.get_by_role("menuitem", name="工作台")


# ==================== pytest fixture: 登录 + 浏览器上下文管理 ====================

@pytest.fixture(scope="session")
def playwright():
    """启动 Playwright 驱动 (整个会话只启动一次)"""
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright):
    """启动 Chromium 浏览器实例 (会话级)"""
    launch_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-setuid-sandbox",
    ]
    browser = playwright.chromium.launch(headless=HEADLESS, args=launch_args)
    yield browser
    browser.close()


@pytest.fixture(scope="session")
def context(browser):
    """
    整个会话只创建一个浏览器上下文 (单次登录, 所有用例共享同一 session).
    ignore_https_errors: 测试环境 (8443) 可能使用自签名证书, 予以忽略.
    locale=zh-CN: 匹配中文界面断言文案.
    viewport: 1800x1300, 避免低分辨率下元素折叠隐藏影响断言.
    """
    context = browser.new_context(
        ignore_https_errors=True,
        locale="zh-CN",
        viewport={"width": 1800, "height": 1300},
    )
    yield context
    context.close()


@pytest.fixture(scope="session")
def logged_in_page(context):
    """
    单次登录并进入工作台页面 (session 级, 所有用例复用同一登录态).
    用例全部执行完成后, 整个会话结束时自动退出并关闭浏览器.
    登录元素定位复用 test_login.py 已验证的 #login / #password / 登录按钮.
    """
    page = context.new_page()
    page.set_default_timeout(15000)

    # ===== 打开登录页 =====
    page.goto(LOGIN_URL, wait_until="networkidle")

    # ===== 登录流程 (复用 test_login.py 已验证的定位器) =====
    username_locator = page.locator("#login")
    password_locator = page.locator("#password")
    login_btn = page.get_by_role("button", name=re.compile(r"登\s*录"))

    # 等待表单可编辑 (SPA 异步初始化可能延迟注册字段)
    expect(username_locator).to_be_editable()

    username_locator.click()
    username_locator.fill(LOGIN_USERNAME)
    expect(username_locator).to_have_value(LOGIN_USERNAME)
    password_locator.click()
    password_locator.fill(LOGIN_PASSWORD)
    expect(password_locator).to_have_value(LOGIN_PASSWORD)
    login_btn.click()

    # 等待登录成功跳转首页 (/dashboard 为工作台默认页)
    expect(page).to_have_url(re.compile(r"/dashboard"), timeout=15000)

    # ===== 工作台为登录后默认首页, 等待 Tab 加载就绪 =====
    expect(tab_workbench(page)).to_be_visible()

    yield page
    page.close()


# ==================== 测试用例 ====================

@allure.feature("工作台菜单")
@allure.label("owner", "自动化测试")
@allure.link("https://stargazer-test.mimiron.cn:8443/login", name="被测系统登录页")
class TestGongZuoTai:
    """观星系统 - 工作台菜单页面 E2E 测试"""

    @pytest.fixture(autouse=True)
    def reset_to_workbench(self, logged_in_page: Page):
        """
        autouse fixture: 每个用例执行前, 统一导航回工作台 /dashboard 并等待 Tab 就绪.
        单次登录模式下用例间共享 page, 必须保证每个用例起始状态一致.
        使用 domcontentloaded + 显式等待元素可见, 比 networkidle 更稳定.
        """
        page = logged_in_page
        page.goto(BASE_URL + "/dashboard", wait_until="domcontentloaded")
        expect(page).to_have_url(re.compile(r"/dashboard"), timeout=15000)
        # 等待工作台 Tab 可见且选中, 确保页面完全加载
        expect(tab_workbench(page)).to_be_visible(timeout=15000)
        expect(tab_workbench(page)).to_have_attribute("aria-selected", "true", timeout=10000)

    # ---------- 1. 三个 Tab 来回切换, 校验选中状态 ----------

    @allure.story("Tab 切换")
    @allure.title("三个 Tab 来回切换, 校验选中状态")
    @allure.severity(allure.severity_level.BLOCKER)
    def test_tab_switch_between_three_tabs(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("校验默认打开工作台 Tab 且为选中状态"):
            expect(tab_workbench(page)).to_be_visible()
            expect(tab_workbench(page)).to_have_attribute("aria-selected", "true", timeout=10000)

        with allure.step("切换到待办中心 Tab, 校验选中"):
            switch_to_tab(tab_todo_center(page))

        with allure.step("切换到测点视图 Tab, 校验选中"):
            switch_to_tab(tab_point_view(page))

        with allure.step("切回工作台 Tab, 校验选中"):
            switch_to_tab(tab_workbench(page))

    # ---------- 2. 工作台 Tab 元素可见校验 ----------

    @allure.story("工作台 Tab")
    @allure.title("工作台: 搜索框 / 快捷按钮 / 日历组件元素可见校验")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_elements_visible(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("校验常用导航区搜索框可见"):
            expect(workbench_search_input(page)).to_be_visible()

        with allure.step("校验快捷功能按钮至少存在一个"):
            # 常用导航区快捷按钮 (具体文案以实际为准, 这里只校验按钮数量 >= 1)
            quick_buttons = page.get_by_role("button")
            expect(quick_buttons.nth(0)).to_be_visible()

        with allure.step("校验运维行事历日历组件可见"):
            expect(calendar_container(page)).to_be_visible()

        with allure.step("校验日历图例可见"):
            expect(calendar_legend(page)).to_be_visible()

        with allure.step("校验日历年月下拉选择器可见"):
            expect(calendar_year_month_select(page)).to_be_visible()

        with allure.step("校验日历月视图切换按钮可见"):
            expect(calendar_month_view_button(page)).to_be_visible()

        with allure.step("校验日历年视图切换按钮可见"):
            expect(calendar_year_view_button(page)).to_be_visible()

        with allure.step("校验日历日期格子至少存在一个"):
            expect(calendar_date_cells(page).first).to_be_visible()

    # ---------- 3. 待办中心 Tab 元素可见校验 ----------

    @allure.story("待办中心 Tab")
    @allure.title("待办中心: 分类树 / 状态标签 / 表格表头 / 查看按钮 / 分页可见")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_todo_center_elements_visible(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("切换到待办中心 Tab"):
            switch_to_tab(tab_todo_center(page))

        with allure.step("校验左侧待办分类树可见"):
            expect(todo_category_tree(page)).to_be_visible()

        with allure.step("校验分类树包含工单 / 审批分类节点"):
            # 待办分类: 工单 + 审批(待我审批 / 我已处理 / 我创建的 / 抄送我的)
            expect(todo_category_tree(page)).to_contain_text("工单")
            expect(todo_category_tree(page)).to_contain_text("待我审批")
            expect(todo_category_tree(page)).to_contain_text("我已处理")
            expect(todo_category_tree(page)).to_contain_text("我创建的")
            expect(todo_category_tree(page)).to_contain_text("抄送我的")

        with allure.step("校验顶部状态标签全部可见"):
            for name in ["全部", "审批中", "审批通过", "审批拒绝"]:
                expect(todo_status_tab(page, name)).to_be_visible()

        with allure.step("校验审批列表表格表头包含全部列名"):
            # 列: 审批ID / 审批标题 / 审批类型 / 发起时间 / 发起人 / 状态 / 操作
            header = todo_table_header(page)
            expect(header).to_contain_text("审批ID")
            expect(header).to_contain_text("审批标题")
            expect(header).to_contain_text("审批类型")
            expect(header).to_contain_text("发起时间")
            expect(header).to_contain_text("发起人")
            expect(header).to_contain_text("状态")
            expect(header).to_contain_text("操作")

        with allure.step("校验操作列【查看】按钮可见"):
            expect(todo_view_button(page)).to_be_visible()

        with allure.step("校验分页控件可见"):
            expect(todo_pagination(page)).to_be_visible()

    # ---------- 4. 测点视图 Tab 元素可见校验 ----------

    @allure.story("测点视图 Tab")
    @allure.title("测点视图: 空间树/测点设备切换可见 + 点击1号楼联动展示测点列表")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_point_view_elements_visible(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("切换到测点视图 Tab"):
            switch_to_tab(tab_point_view(page))

        with allure.step("校验左栏空间树可见"):
            expect(space_tree(page)).to_be_visible(timeout=15000)

        with allure.step("校验右栏'测点/设备'切换控件可见且'测点'默认选中"):
            expect(point_segmented_item(page, "测点")).to_be_visible(timeout=15000)
            expect(point_segmented_item(page, "测点")).to_have_class(
                re.compile(r".*ant-segmented-item-selected.*")
            )
            expect(point_segmented_item(page, "设备")).to_be_visible()

        with allure.step("左侧空间栏点击'1号楼'节点, 校验右栏联动展示测点列表"):
            node = space_tree_node(page, "1号楼")
            node.wait_for(state="visible", timeout=15000)
            node.click()
            page.wait_for_timeout(3000)
            # 点击后右栏切换控件仍可见 (联动刷新)
            expect(point_segmented_item(page, "测点")).to_be_visible()
            # 测点列表联动: 有数据显示表格, 无数据显示暂无数据占位
            assert page.locator(".ant-table").first.is_visible() or point_empty(page).is_visible(), \
                "点击1号楼后右栏既无测点表格也无暂无数据占位"

    # ---------- 5. 待办中心状态标签切换 ----------

    @allure.story("待办中心状态切换")
    @allure.title("待办中心: 状态标签切换并校验选中状态")
    @allure.severity(allure.severity_level.NORMAL)
    def test_todo_center_status_tabs_switching(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("切换到待办中心 Tab"):
            switch_to_tab(tab_todo_center(page))

        with allure.step("依次点击状态标签并校验选中"):
            # 状态标签为 ant-radio-button-wrapper, 选中态通过 checked 类标记
            for name in ["审批中", "审批通过", "审批拒绝", "全部"]:
                tab = todo_status_tab(page, name)
                tab.wait_for(state="visible", timeout=10000)
                tab.click()
                expect(tab).to_have_class(re.compile(r".*ant-radio-button-wrapper-checked.*"), timeout=10000)

    # ---------- 6. 测点视图 点击1号楼 + 设备页结构校验 ----------

    @allure.story("测点视图-设备页")
    @allure.title("测点视图: 点击1号楼 -> 切换设备页 -> 设备类型树/GUID/设备名称/重置/查询/表格/分页校验")
    @allure.severity(allure.severity_level.NORMAL)
    def test_point_view_query_and_reset(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("切换到测点视图 Tab"):
            switch_to_tab(tab_point_view(page))

        with allure.step("左侧空间栏点击'1号楼'节点"):
            node = space_tree_node(page, "1号楼")
            node.wait_for(state="visible", timeout=15000)
            node.click()
            page.wait_for_timeout(2000)

        with allure.step("点击'设备'切换控件, 校验选中 + 设备页结构可见"):
            dev_item = point_segmented_item(page, "设备")
            dev_item.wait_for(state="visible", timeout=15000)
            dev_item.click()
            expect(dev_item).to_have_class(
                re.compile(r".*ant-segmented-item-selected.*"), timeout=10000
            )

        with allure.step("校验设备类型树可见"):
            expect(device_type_tree(page)).to_be_visible(timeout=10000)

        with allure.step("校验GUID搜索框可见"):
            expect(device_guid_input(page)).to_be_visible()

        with allure.step("校验设备名称搜索框可见"):
            expect(device_name_input(page)).to_be_visible()

        with allure.step("校验重置/查询按钮可见"):
            expect(device_reset_button(page)).to_be_visible()
            expect(device_query_button(page)).to_be_visible()

        with allure.step("校验设备数据列表表头字段: GUID/设备名称/设备房间/设备类型/厂商/型号/启用状态"):
            header = device_table_header(page)
            expect(header).to_contain_text("GUID")
            expect(header).to_contain_text("设备名称")
            expect(header).to_contain_text("设备房间")
            expect(header).to_contain_text("设备类型")
            expect(header).to_contain_text("厂商")
            expect(header).to_contain_text("型号")
            expect(header).to_contain_text("启用状态")

        with allure.step("校验分页控件可见"):
            expect(device_pagination(page)).to_be_visible()

    # ========================================================================
    # 以下为工作台常用导航区快捷入口跳转测试 (7~14)
    # ========================================================================

    # ---------- 7. 工作台搜索告警盯屏并跳转 ----------

    @allure.story("工作台搜索告警盯屏")
    @allure.title("工作台: 搜索'告警盯屏' -> 点击跳转 -> 校验状态看板 -> 返回")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_search_and_nav_alert_screen(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("在常用导航搜索框输入'告警盯屏'"):
            search = workbench_search_input(page)
            search.click()
            search.fill("告警盯屏")

        with allure.step("校验搜索结果只显示告警盯屏"):
            # 搜索后, 快捷导航区仅保留匹配项 "告警盯屏"
            expect(quick_nav_item(page, "告警盯屏")).to_be_visible()
            # 其他快捷入口应被过滤 (不可见)
            for name in ["考试管理", "事件列表", "变更列表", "风险登记册"]:
                expect(quick_nav_item(page, name)).not_to_be_visible()

        with allure.step("点击'告警盯屏', 校验页面跳转至告警盯屏菜单栏"):
            quick_nav_item(page, "告警盯屏").click()
            # 告警盯屏 URL: /mon/alarm-dashboard/kanban
            expect(page).to_have_url(re.compile(r"/mon/alarm-dashboard"), timeout=15000)

        with allure.step("校验状态看板 Tab 可见且为选中状态"):
            expect(alarm_screen_tab(page, "状态看板")).to_be_visible()
            expect(alarm_screen_tab(page, "状态看板")).to_have_attribute("aria-selected", "true", timeout=10000)

        with allure.step("页面返回操作, 重新返回至工作台菜单栏, 工作台 Tab"):
            navigate_back_to_workbench(page)

    # ---------- 8. 工作台导航 -> 考试管理 ----------

    @allure.story("工作台导航-考试管理")
    @allure.title("工作台: 点击考试管理 -> 校验分类树/查询条件/表格/按钮 -> 返回")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_nav_exam_management(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("点击'考试管理'连接, 校验页面跳转至考试管理菜单栏"):
            quick_nav_item(page, "考试管理").click()
            # 考试管理 URL: /exam-center/exams
            expect(page).to_have_url(re.compile(r"/exam-center"), timeout=15000)

        with allure.step("校验左侧考试分类结构树可见"):
            expect(exam_category_tree(page)).to_be_visible()
            # 树节点包含 "全量考试" (带数量统计)
            expect(exam_category_tree(page)).to_contain_text("全量考试")

        with allure.step("校验查询条件: 考试名称 / 考试分类 / 考试状态 / 考试时间"):
            # 查询表单标签 (ant-form-item-label)
            expect(exam_form_label(page, "考试名称")).to_be_visible()
            expect(exam_form_label(page, "考试分类")).to_be_visible()
            expect(exam_form_label(page, "考试状态")).to_be_visible()
            expect(exam_form_label(page, "考试时间")).to_be_visible()

        with allure.step("校验重置 / 查询按钮可见"):
            expect(list_page_reset_button(page)).to_be_visible()
            expect(list_page_query_button(page)).to_be_visible()

        with allure.step("校验创建考试按钮可见"):
            expect(list_page_create_button(page, "创建考试")).to_be_visible()

        with allure.step("校验考试列表表格表头包含列名"):
            header = list_page_table_header(page)
            expect(header).to_contain_text("考试名称")
            expect(header).to_contain_text("考试状态")
            expect(header).to_contain_text("考试时间")
            expect(header).to_contain_text("操作")

        with allure.step("校验分页控件可见"):
            expect(list_page_pagination(page)).to_be_visible()

        with allure.step("页面返回操作, 重新返回至工作台菜单栏, 工作台 Tab"):
            navigate_back_to_workbench(page)

    # ---------- 9. 工作台导航 -> 事件列表 ----------

    @allure.story("工作台导航-事件列表")
    @allure.title("工作台: 点击事件列表 -> 校验表格/按钮 -> 返回")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_nav_event_list(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("点击'事件列表', 校验页面跳转至事件列表菜单栏"):
            quick_nav_item(page, "事件列表").click()
            # 事件列表 URL: /event
            expect(page).to_have_url(re.compile(r"/event"), timeout=15000)

        with allure.step("校验事件列表表格表头包含列名"):
            # 列: 事件ID / 事件名称 / 事件描述 / 事件类别 / 事件状态 / 操作
            header = list_page_table_header(page)
            expect(header).to_contain_text("事件ID")
            expect(header).to_contain_text("事件名称")
            expect(header).to_contain_text("事件描述")
            expect(header).to_contain_text("事件类别")
            expect(header).to_contain_text("事件状态")
            expect(header).to_contain_text("操作")

        with allure.step("校验分页控件可见"):
            expect(list_page_pagination(page)).to_be_visible()

        with allure.step("校验重置 / 查询 / 展开 / 创建事件 / 导出 按钮元素可见"):
            expect(list_page_reset_button(page)).to_be_visible()
            expect(list_page_query_button(page)).to_be_visible()
            expect(list_page_expand_link(page)).to_be_visible()
            expect(list_page_create_button(page, "创建事件")).to_be_visible()
            expect(list_page_export_button(page)).to_be_visible()

        with allure.step("页面返回操作, 重新返回至工作台菜单栏, 工作台 Tab"):
            navigate_back_to_workbench(page)

    # ---------- 10. 工作台导航 -> 变更列表 ----------

    @allure.story("工作台导航-变更列表")
    @allure.title("工作台: 点击变更列表 -> 校验表格/按钮 -> 返回")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_nav_change_list(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("点击'变更列表', 校验页面跳转至变更列表菜单栏"):
            quick_nav_item(page, "变更列表").click()
            # 变更列表 URL: /change
            expect(page).to_have_url(re.compile(r"/change"), timeout=15000)

        with allure.step("校验变更列表表格表头包含列名"):
            # 列: 变更ID / 变更标题(事件标题) / 变更等级 / 变更专业 / 变更状态 / 操作
            header = list_page_table_header(page)
            expect(header).to_contain_text("变更ID")
            expect(header).to_contain_text("变更标题")
            expect(header).to_contain_text("变更等级")
            expect(header).to_contain_text("变更专业")
            expect(header).to_contain_text("变更状态")
            expect(header).to_contain_text("操作")

        with allure.step("校验分页控件可见"):
            expect(list_page_pagination(page)).to_be_visible()

        with allure.step("校验重置 / 查询 / 展开 / 创建变更 / 导出 按钮元素可见"):
            expect(list_page_reset_button(page)).to_be_visible()
            expect(list_page_query_button(page)).to_be_visible()
            expect(list_page_expand_link(page)).to_be_visible()
            expect(list_page_create_button(page, "创建变更")).to_be_visible()
            expect(list_page_export_button(page)).to_be_visible()

        with allure.step("页面返回操作, 重新返回至工作台菜单栏, 工作台 Tab"):
            navigate_back_to_workbench(page)

    # ---------- 11. 工作台导航 -> 风险登记册 ----------

    @allure.story("工作台导航-风险登记册")
    @allure.title("工作台: 点击风险登记册 -> 校验表格/按钮 -> 返回")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_nav_risk_register(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("点击'风险登记册', 校验页面跳转至风险登记册菜单栏"):
            quick_nav_item(page, "风险登记册").click()
            # 风险登记册 URL: /risk
            expect(page).to_have_url(re.compile(r"/risk"), timeout=15000)

        with allure.step("校验风险登记册表格表头包含列名"):
            # 列: 风险ID / 风险标题 / 风险等级 / 风险类型 / 风险状态 / 措施进度 / 操作
            header = list_page_table_header(page)
            expect(header).to_contain_text("风险ID")
            expect(header).to_contain_text("风险标题")
            expect(header).to_contain_text("风险等级")
            expect(header).to_contain_text("风险类型")
            expect(header).to_contain_text("风险状态")
            expect(header).to_contain_text("措施进度")
            expect(header).to_contain_text("操作")

        with allure.step("校验分页控件可见"):
            expect(list_page_pagination(page)).to_be_visible()

        with allure.step("校验重置 / 查询 / 展开 / 创建风险 / 导出 按钮元素可见"):
            expect(list_page_reset_button(page)).to_be_visible()
            expect(list_page_query_button(page)).to_be_visible()
            expect(list_page_expand_link(page)).to_be_visible()
            expect(list_page_create_button(page, "创建风险")).to_be_visible()
            expect(list_page_export_button(page)).to_be_visible()

        with allure.step("页面返回操作, 重新返回至工作台菜单栏, 工作台 Tab"):
            navigate_back_to_workbench(page)

    # ---------- 12. 工作台导航 -> 维护工单 ----------

    @allure.story("工作台导航-维护工单")
    @allure.title("工作台: 点击维护工单 -> 校验表格/按钮 -> 返回")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_nav_maintain_workorder(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("点击'维护工单', 校验页面跳转至维护工单菜单栏"):
            quick_nav_item(page, "维护工单").click()
            # 维护工单 URL: /task/maintain
            expect(page).to_have_url(re.compile(r"/task/maintain"), timeout=15000)

        with allure.step("校验维护工单表格表头包含列名"):
            # 列: 工单编号 / 工单标题 / 工单子类型 / 位置 / 进度 / 状态 / 操作
            header = workorder_table_header(page)
            expect(header).to_contain_text("工单编号")
            expect(header).to_contain_text("工单标题")
            expect(header).to_contain_text("工单子类型")
            expect(header).to_contain_text("位置")
            expect(header).to_contain_text("进度")
            expect(header).to_contain_text("操作")

        with allure.step("校验分页控件可见"):
            expect(workorder_pagination(page)).to_be_visible()

        with allure.step("校验重置 / 查询 / 展开 / 创建维护工单 / 导出 按钮元素可见"):
            expect(list_page_reset_button(page)).to_be_visible()
            expect(list_page_query_button(page)).to_be_visible()
            expect(list_page_expand_link(page)).to_be_visible()
            expect(list_page_create_button(page, "创建维护工单")).to_be_visible()
            expect(list_page_export_button(page)).to_be_visible()

        with allure.step("页面返回操作, 重新返回至工作台菜单栏, 工作台 Tab"):
            navigate_back_to_workbench(page)

    # ---------- 13. 工作台导航 -> 上下电工单 ----------

    @allure.story("工作台导航-上下电工单")
    @allure.title("工作台: 点击上下电工单 -> 校验表格/按钮 -> 返回")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_nav_power_workorder(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("点击'上下电工单', 校验页面跳转至上下电工单菜单栏"):
            quick_nav_item(page, "上下电工单").click()
            # 上下电工单 URL: /task/power
            expect(page).to_have_url(re.compile(r"/task/power"), timeout=15000)

        with allure.step("校验上下电工单表格表头包含列名"):
            # 列: 工单编号 / 工单标题 / 工单子类型 / 创建时间 / 进度 / 操作
            header = workorder_table_header(page)
            expect(header).to_contain_text("工单编号")
            expect(header).to_contain_text("工单标题")
            expect(header).to_contain_text("工单子类型")
            expect(header).to_contain_text("创建时间")
            expect(header).to_contain_text("进度")
            expect(header).to_contain_text("操作")

        with allure.step("校验分页控件可见"):
            expect(workorder_pagination(page)).to_be_visible()

        with allure.step("校验重置 / 查询 / 展开 / 创建上下电工单 按钮元素可见"):
            expect(list_page_reset_button(page)).to_be_visible()
            expect(list_page_query_button(page)).to_be_visible()
            expect(list_page_expand_link(page)).to_be_visible()
            expect(list_page_create_button(page, "创建上下电工单")).to_be_visible()

        with allure.step("页面返回操作, 重新返回至工作台菜单栏, 工作台 Tab"):
            navigate_back_to_workbench(page)

    # ---------- 14. 工作台导航 -> 巡检工单 ----------

    @allure.story("工作台导航-巡检工单")
    @allure.title("工作台: 点击巡检工单 -> 校验表格/按钮 -> 返回")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_nav_inspection_workorder(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("点击'巡检工单', 校验页面跳转至巡检工单菜单栏"):
            quick_nav_item(page, "巡检工单").click()
            # 巡检工单 URL: /task/inspection
            expect(page).to_have_url(re.compile(r"/task/inspection"), timeout=15000)

        with allure.step("校验巡检工单表格表头包含列名"):
            # 列: 工单编号 / 工单标题 / 工单子类型 / 位置 / 进度 / 状态 / 操作
            header = workorder_table_header(page)
            expect(header).to_contain_text("工单编号")
            expect(header).to_contain_text("工单标题")
            expect(header).to_contain_text("工单子类型")
            expect(header).to_contain_text("位置")
            expect(header).to_contain_text("进度")
            expect(header).to_contain_text("操作")

        with allure.step("校验分页控件可见"):
            expect(workorder_pagination(page)).to_be_visible()

        with allure.step("校验重置 / 查询 / 展开 / 创建巡检工单 按钮元素可见"):
            expect(list_page_reset_button(page)).to_be_visible()
            expect(list_page_query_button(page)).to_be_visible()
            expect(list_page_expand_link(page)).to_be_visible()
            expect(list_page_create_button(page, "创建巡检工单")).to_be_visible()

        with allure.step("页面返回操作, 重新返回至工作台菜单栏, 工作台 Tab"):
            navigate_back_to_workbench(page)

    # ========================================================================
    # 以下为边界场景测试 (15~22)
    # ========================================================================

    # ---------- 15. 工作台搜索无结果 ----------

    @allure.story("工作台搜索-无结果")
    @allure.title("边界: 搜索不存在的名称, 校验所有快捷入口不可见")
    @allure.severity(allure.severity_level.NORMAL)
    def test_workbench_search_no_result(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("在搜索框输入不存在的名称'不存在的功能XYZ'"):
            search = workbench_search_input(page)
            search.click()
            search.fill("不存在的功能XYZ")

        with allure.step("校验所有快捷入口均不可见 (无匹配项)"):
            for name in ["告警盯屏", "考试管理", "事件列表", "变更列表", "风险登记册",
                         "维护工单", "上下电工单", "巡检工单"]:
                expect(quick_nav_item(page, name)).not_to_be_visible()

    # ---------- 16. 工作台搜索清空后恢复 ----------

    @allure.story("工作台搜索-清空恢复")
    @allure.title("边界: 搜索后清空搜索框, 校验所有快捷入口恢复可见")
    @allure.severity(allure.severity_level.NORMAL)
    def test_workbench_search_clear_restore(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("先搜索'告警盯屏', 校验仅显示告警盯屏"):
            search = workbench_search_input(page)
            search.click()
            search.fill("告警盯屏")
            expect(quick_nav_item(page, "告警盯屏")).to_be_visible()
            expect(quick_nav_item(page, "考试管理")).not_to_be_visible()

        with allure.step("清空搜索框, 校验所有快捷入口恢复可见"):
            search.fill("")
            for name in ["告警盯屏", "考试管理", "事件列表", "变更列表", "风险登记册",
                         "维护工单", "上下电工单", "巡检工单"]:
                expect(quick_nav_item(page, name)).to_be_visible()

    # ---------- 17. 工作台搜索特殊字符 ----------

    @allure.story("工作台搜索-特殊字符")
    @allure.title("边界: 搜索特殊字符(XSS/SQL), 校验系统不报错且快捷入口可见")
    @allure.severity(allure.severity_level.NORMAL)
    def test_workbench_search_special_chars(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("搜索含 XSS 和 SQL 注入字符的字符串"):
            # 特殊字符: <script>alert(1)</script> 和 ' OR 1=1 --
            search = workbench_search_input(page)
            search.click()
            search.fill("<script>alert(1)</script>' OR 1=1 --")

        with allure.step("校验系统未崩溃 (搜索框仍可见, 快捷入口不可见)"):
            expect(workbench_search_input(page)).to_be_visible()
            # 特殊字符无匹配, 所有快捷入口不可见
            expect(quick_nav_item(page, "告警盯屏")).not_to_be_visible()

        with allure.step("清空搜索框, 校验快捷入口恢复"):
            search.fill("")
            expect(quick_nav_item(page, "告警盯屏")).to_be_visible()

    # ---------- 18. Tab 快速连续切换 ----------

    @allure.story("Tab 切换-快速连续")
    @allure.title("边界: 快速连续切换三个 Tab, 校验最终选中最后一个")
    @allure.severity(allure.severity_level.NORMAL)
    def test_tab_rapid_switch(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("快速连续切换: 工作台 -> 待办中心 -> 测点视图 -> 工作台 -> 待办中心"):
            # 使用 switch_to_tab (含重试机制), 避免 SPA DOM detached 导致 click 失效
            # 每次切换后短暂等待 500ms 让 DOM 重新挂载稳定
            for target in [tab_workbench(page), tab_todo_center(page),
                           tab_point_view(page), tab_workbench(page),
                           tab_todo_center(page)]:
                switch_to_tab(target, max_retries=5)
                page.wait_for_timeout(500)

        with allure.step("校验最终待办中心 Tab 为选中状态"):
            expect(tab_todo_center(page)).to_have_attribute("aria-selected", "true", timeout=10000)

    # ---------- 19. 重复点击已选中 Tab ----------

    @allure.story("Tab 切换-重复点击")
    @allure.title("边界: 重复点击已选中 Tab, 校验选中状态保持")
    @allure.severity(allure.severity_level.NORMAL)
    def test_tab_reclick_selected(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("切换到待办中心 Tab 并校验选中"):
            switch_to_tab(tab_todo_center(page))

        with allure.step("重复点击待办中心 Tab 3 次, 校验选中状态保持"):
            for _ in range(3):
                tab_todo_center(page).click()
            expect(tab_todo_center(page)).to_have_attribute("aria-selected", "true", timeout=10000)

    # ---------- 20. 测点视图 测点/设备快速切换 ----------

    @allure.story("测点视图-快速切换")
    @allure.title("边界: 快速切换测点/设备, 校验选中状态正确")
    @allure.severity(allure.severity_level.NORMAL)
    def test_point_view_query_without_conditions(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("切换到测点视图 Tab"):
            switch_to_tab(tab_point_view(page))

        with allure.step("快速切换 测点 -> 设备 -> 测点 -> 设备, 校验选中状态"):
            for target in ["设备", "测点", "设备", "测点"]:
                item = point_segmented_item(page, target)
                item.wait_for(state="visible", timeout=15000)
                item.click()
                expect(item).to_have_class(
                    re.compile(r".*ant-segmented-item-selected.*"), timeout=10000
                )

    # ---------- 21. 待办中心重复点击同一状态标签 ----------

    @allure.story("待办中心-重复点击状态")
    @allure.title("边界: 重复点击同一状态标签, 校验选中状态保持")
    @allure.severity(allure.severity_level.NORMAL)
    def test_todo_status_reclick_same(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("切换到待办中心 Tab"):
            switch_to_tab(tab_todo_center(page))

        with allure.step("点击'审批中'状态标签并校验选中"):
            tab = todo_status_tab(page, "审批中")
            tab.click()
            expect(tab).to_have_class(re.compile(r".*ant-radio-button-wrapper-checked.*"), timeout=10000)

        with allure.step("重复点击'审批中'状态标签 3 次, 校验选中状态保持"):
            for _ in range(3):
                tab.click()
            expect(tab).to_have_class(re.compile(r".*ant-radio-button-wrapper-checked.*"), timeout=10000)

    # ---------- 22. 日历月/年视图切换 ----------

    @allure.story("日历-视图切换")
    @allure.title("边界: 月/年视图来回切换, 校验切换后元素可见")
    @allure.severity(allure.severity_level.NORMAL)
    def test_calendar_view_switch(self, logged_in_page: Page):
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("点击年视图切换按钮, 校验年视图按钮选中"):
            calendar_year_view_button(page).click()
            expect(calendar_year_view_button(page)).to_have_class(
                re.compile(r".*ant-radio-button-wrapper-checked.*"), timeout=10000
            )

        with allure.step("点击月视图切换按钮, 校验月视图按钮选中"):
            calendar_month_view_button(page).click()
            expect(calendar_month_view_button(page)).to_have_class(
                re.compile(r".*ant-radio-button-wrapper-checked.*"), timeout=10000
            )

        with allure.step("校验日历组件和日期格子仍可见"):
            expect(calendar_container(page)).to_be_visible()
            expect(calendar_date_cells(page).first).to_be_visible()

    # ---------- 23. 工作台 -> 审批中心 -> 待我审批数字跳转 ----------

    @allure.story("审批中心导航")
    @allure.title("审批中心: 卡片元素可见 + 点击待我审批数字跳转 + 查询表单/表格可见 + 返回")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_approval_center_elements(self, logged_in_page: Page):
        """覆盖: 审批中心4卡片可见 + 查询表单/表格/分页可见"""
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("校验审批中心4个统计卡片可见 (待我审批/我已处理/我发起的/我收到的)"):
            for label in ["待我审批", "我已处理", "我发起的", "我收到的"]:
                expect(approval_center_card(page, label)).to_be_visible(timeout=10000)

    @allure.story("审批中心导航")
    @allure.title("审批中心: 点击待我审批数字 -> 跳转待我审批Tab高亮 + 查询表单/表格可见 + 返回工作台")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_approval_nav_pending(self, logged_in_page: Page):
        """覆盖: 点击待我审批数字链接 -> Tab高亮 + 数字一致 + 查询条件/表头/分页可见 + 返回"""
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("获取待我审批卡片数字并点击数字链接"):
            link = approval_center_number_link(page, "待我审批")
            expect(link).to_be_visible(timeout=10000)
            # 等待数字加载完成 (初始为0, 异步加载后显示真实数字; 等待数字 > 0 或多位数字)
            expect(link).to_have_text(re.compile(r"[1-9]\d*"), timeout=15000)
            num_before = link.inner_text()
            link.click()

        with allure.step("校验跳转后待我审批 Radio Tab 高亮选中"):
            radio = approval_radio_tab(page, "待我审批")
            expect(radio).to_be_visible(timeout=10000)
            expect(radio).to_have_class(
                re.compile(r".*ant-radio-button-wrapper-checked.*"), timeout=10000
            )

        with allure.step("校验 Radio Tab 括号中数字与点击的数字一致"):
            # 等待 radio 文本中出现括号数字 (SPA 异步加载, 数字可能延迟渲染)
            expect(radio).to_have_text(re.compile(r".*\(\d+\).*"), timeout=10000)
            radio_text = radio.inner_text()
            match = re.search(r"\((\d+)\)", radio_text)
            assert match, f"未在 radio 文本中找到括号数字: {radio_text!r}"
            num_after = match.group(1)
            assert num_after == num_before, f"数字不一致: 卡片={num_before!r} radio={num_after!r}"

        with allure.step("若查询表单为折叠状态, 先点击展开"):
            expand_link = page.locator("a", has_text="展开")
            if expand_link.count() > 0 and expand_link.first.is_visible():
                expand_link.first.click()

        with allure.step("校验查询表单元素可见 (审批ID/审批标题/审批类型/状态)"):
            for label_text in ["审批ID", "审批标题", "审批类型", "状态"]:
                expect(approval_form_label(page, label_text)).to_be_visible()

        with allure.step("校验重置/查询按钮可见"):
            expect(approval_reset_button(page)).to_be_visible()
            expect(approval_query_button(page)).to_be_visible()

        with allure.step("校验收起链接可见 (表单已展开)"):
            expect(approval_collapse_link(page)).to_be_visible()

        with allure.step("校验列表表头列名可见"):
            expect(approval_table_header(page)).to_be_visible()
            expect(approval_table_header(page)).to_contain_text("审批ID")
            expect(approval_table_header(page)).to_contain_text("审批标题")
            expect(approval_table_header(page)).to_contain_text("审批类型")
            expect(approval_table_header(page)).to_contain_text("发起人")
            expect(approval_table_header(page)).to_contain_text("状态")

        with allure.step("校验分页控件可见"):
            expect(approval_pagination(page)).to_be_visible()

        with allure.step("返回工作台菜单栏, 校验工作台 Tab 选中"):
            workbench_menu_item(page).click()
            expect(page).to_have_url(re.compile(r"/dashboard"), timeout=15000)
            expect(tab_workbench(page)).to_have_attribute("aria-selected", "true", timeout=10000)

    @allure.story("审批中心导航")
    @allure.title("审批中心: 点击我已处理数字 -> 跳转我已处理Tab高亮 + 返回工作台")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_approval_nav_processed(self, logged_in_page: Page):
        """覆盖: 点击我已处理数字链接 -> Tab高亮 + 数字一致 + 返回"""
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("获取我已处理卡片数字并点击数字链接"):
            link = approval_center_number_link(page, "我已处理")
            expect(link).to_be_visible(timeout=10000)
            # 等待数字加载完成 (初始为0, 异步加载后显示真实数字; 等待非零数字)
            expect(link).to_have_text(re.compile(r"[1-9]\d*"), timeout=15000)
            num_before = link.inner_text()
            link.click()

        with allure.step("校验跳转后我已处理 Radio Tab 高亮选中"):
            radio = approval_radio_tab(page, "我已处理")
            expect(radio).to_be_visible(timeout=10000)
            expect(radio).to_have_class(
                re.compile(r".*ant-radio-button-wrapper-checked.*"), timeout=10000
            )

        with allure.step("校验 Radio Tab 括号中数字与点击的数字一致"):
            # 等待 radio 文本中出现括号数字 (SPA 异步加载, 数字可能延迟渲染)
            expect(radio).to_have_text(re.compile(r".*\(\d+\).*"), timeout=10000)
            radio_text = radio.inner_text()
            match = re.search(r"\((\d+)\)", radio_text)
            assert match, f"未在 radio 文本中找到括号数字: {radio_text!r}"
            num_after = match.group(1)
            assert num_after == num_before, f"数字不一致: 卡片={num_before!r} radio={num_after!r}"

        with allure.step("返回工作台菜单栏, 校验工作台 Tab 选中"):
            workbench_menu_item(page).click()
            expect(page).to_have_url(re.compile(r"/dashboard"), timeout=15000)
            expect(tab_workbench(page)).to_have_attribute("aria-selected", "true", timeout=10000)

    @allure.story("审批中心导航")
    @allure.title("审批中心: 点击我发起的数字 -> 跳转我创建的Tab高亮 + 返回工作台")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_approval_nav_created(self, logged_in_page: Page):
        """覆盖: 点击我发起的数字链接 -> 跳转我创建的Tab高亮 + 数字一致 + 返回"""
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("获取我发起的卡片数字并点击数字链接"):
            link = approval_center_number_link(page, "我发起的")
            expect(link).to_be_visible(timeout=10000)
            # 等待数字加载完成 (初始为0, 异步加载后显示真实数字; 等待非零数字)
            expect(link).to_have_text(re.compile(r"[1-9]\d*"), timeout=15000)
            num_before = link.inner_text()
            link.click()

        with allure.step("校验跳转后我创建的 Radio Tab 高亮选中 (卡片'我发起的'对应Tab'我创建的')"):
            radio = approval_radio_tab(page, "我创建的")
            expect(radio).to_be_visible(timeout=10000)
            expect(radio).to_have_class(
                re.compile(r".*ant-radio-button-wrapper-checked.*"), timeout=10000
            )

        with allure.step("校验 Radio Tab 括号中数字与点击的数字一致"):
            # 等待 radio 文本中出现括号数字 (SPA 异步加载, 数字可能延迟渲染)
            expect(radio).to_have_text(re.compile(r".*\(\d+\).*"), timeout=10000)
            radio_text = radio.inner_text()
            match = re.search(r"\((\d+)\)", radio_text)
            assert match, f"未在 radio 文本中找到括号数字: {radio_text!r}"
            num_after = match.group(1)
            assert num_after == num_before, f"数字不一致: 卡片={num_before!r} radio={num_after!r}"

        with allure.step("返回工作台菜单栏, 校验工作台 Tab 选中"):
            workbench_menu_item(page).click()
            expect(page).to_have_url(re.compile(r"/dashboard"), timeout=15000)
            expect(tab_workbench(page)).to_have_attribute("aria-selected", "true", timeout=10000)

    @allure.story("审批中心导航")
    @allure.title("审批中心: 点击我收到的数字 -> 跳转抄送我的Tab高亮 + 返回工作台")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_approval_nav_cc(self, logged_in_page: Page):
        """覆盖: 点击我收到的数字链接 -> 跳转抄送我的Tab高亮 + 数字一致 + 返回"""
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("获取我收到的卡片数字并点击数字链接"):
            link = approval_center_number_link(page, "我收到的")
            expect(link).to_be_visible(timeout=10000)
            # 等待数字加载完成 (初始为0, 异步加载后显示真实数字; 等待非零数字)
            expect(link).to_have_text(re.compile(r"[1-9]\d*"), timeout=15000)
            num_before = link.inner_text()
            link.click()

        with allure.step("校验跳转后抄送我的 Radio Tab 高亮选中 (卡片'我收到的'对应Tab'抄送我的')"):
            radio = approval_radio_tab(page, "抄送我的")
            expect(radio).to_be_visible(timeout=10000)
            expect(radio).to_have_class(
                re.compile(r".*ant-radio-button-wrapper-checked.*"), timeout=10000
            )

        with allure.step("校验 Radio Tab 括号中数字与点击的数字一致"):
            # 等待 radio 文本中出现括号数字 (SPA 异步加载, 数字可能延迟渲染)
            expect(radio).to_have_text(re.compile(r".*\(\d+\).*"), timeout=10000)
            radio_text = radio.inner_text()
            match = re.search(r"\((\d+)\)", radio_text)
            assert match, f"未在 radio 文本中找到括号数字: {radio_text!r}"
            num_after = match.group(1)
            assert num_after == num_before, f"数字不一致: 卡片={num_before!r} radio={num_after!r}"

        with allure.step("返回工作台菜单栏, 校验工作台 Tab 选中"):
            workbench_menu_item(page).click()
            expect(page).to_have_url(re.compile(r"/dashboard"), timeout=15000)
            expect(tab_workbench(page)).to_have_attribute("aria-selected", "true", timeout=10000)

    @allure.story("审批中心导航")
    @allure.title("审批中心: 跳转后Radio Tab来回切换, 校验高亮状态")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_approval_radio_switch(self, logged_in_page: Page):
        """覆盖: 跳转后分别点击 待我审批/我已处理/我创建的 Radio Tab, 校验高亮"""
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("点击待我审批数字链接进入审批列表"):
            approval_center_number_link(page, "待我审批").click()

        with allure.step("点击我已处理 Radio Tab, 校验高亮"):
            radio = approval_radio_tab(page, "我已处理")
            radio.click()
            expect(radio).to_have_class(
                re.compile(r".*ant-radio-button-wrapper-checked.*"), timeout=10000
            )

        with allure.step("点击我创建的 Radio Tab, 校验高亮"):
            radio = approval_radio_tab(page, "我创建的")
            radio.click()
            expect(radio).to_have_class(
                re.compile(r".*ant-radio-button-wrapper-checked.*"), timeout=10000
            )

        with allure.step("点击待我审批 Radio Tab, 校验高亮"):
            radio = approval_radio_tab(page, "待我审批")
            radio.click()
            expect(radio).to_have_class(
                re.compile(r".*ant-radio-button-wrapper-checked.*"), timeout=10000
            )

        with allure.step("点击左侧菜单工作台, 返回工作台菜单栏, 校验工作台 Tab 选中"):
            workbench_menu_item(page).click()
            expect(page).to_have_url(re.compile(r"/dashboard"), timeout=15000)
            expect(tab_workbench(page)).to_have_attribute("aria-selected", "true", timeout=10000)

    # ---------- 29. 工作台 -> 运维工单卡片元素可见 ----------

    @allure.story("运维工单导航")
    @allure.title("运维工单: 8个分类卡片元素/字段/数据可见")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_om_cards_visible(self, logged_in_page: Page):
        """覆盖: 运维工单元素框中 事件管理/变更管理/风险管理/演练管理/上下电管理
        /维护管理/维修管理/待下发工单 8 个卡片: 元素(卡片)、字段(标题)、数据(数字)可见"""
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("校验运维工单 8 个统计卡片可见 (元素=卡片 / 字段=标题 / 数据=数字链接)"):
            for label in ["事件管理", "变更管理", "风险管理", "演练管理",
                          "上下电管理", "维护管理", "维修管理", "待下发工单"]:
                card = om_card(page, label)
                # 元素: 卡片容器可见
                expect(card).to_be_visible(timeout=10000)
                # 字段: 卡片标题文本为对应分类名
                expect(card.locator(".ant-statistic-title")).to_have_text(label)
                # 数据: 卡片内数字链接可见 (含数字, 异步加载后显示真实统计值)
                num_link = card.locator("a").first
                expect(num_link).to_be_visible()
                expect(num_link).to_contain_text(re.compile(r"\d+"))

    # ---------- 30. 工作台 -> 运维工单 -> 事件管理数字跳转事件列表 ----------

    @allure.story("运维工单导航")
    @allure.title("运维工单: 点击事件管理数字 -> 跳转事件列表 + 展开收起 + 表头/横向滚动校验 + 返回工作台")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_workbench_om_nav_event_list(self, logged_in_page: Page):
        """覆盖: 点击事件管理数字链接跳转事件列表 -> 收起态3项查询条件/按钮/分页可见
        -> 展开后8项查询条件可见 -> 收起恢复3项 -> 表头字段校验
        -> 横向滚动到最后校验右侧列 -> 点击左侧菜单工作台返回"""
        page = logged_in_page

        with allure.step("确保停留在工作台 Tab"):
            switch_to_tab(tab_workbench(page))

        with allure.step("点击'事件管理'数字链接, 校验页面跳转至事件列表菜单页"):
            link = om_number_link(page, "事件管理")
            expect(link).to_be_visible(timeout=10000)
            link.click()
            # 事件管理数字链接 URL: /event?filters[...] (带 taskStatus 过滤条件)
            expect(page).to_have_url(re.compile(r"/event"), timeout=15000)

        with allure.step("校验收起状态: 仅展示 事件名称/事件类型/事件等级 三项查询条件"):
            # 收起时可见的 3 项
            for label_text in ["事件名称", "事件类型", "事件等级"]:
                expect(event_form_label(page, label_text)).to_be_visible()
            # 其余查询条件应隐藏 (收起态不展示)
            for hidden_label in ["事件ID", "事件来源", "事件状态", "楼栋", "机柜影响",
                                 "责任人", "创建人", "设备类型", "故障设备"]:
                expect(event_form_label(page, hidden_label)).not_to_be_visible()

        with allure.step("校验重置/查询/展开/创建事件/导出按钮及分页控件可见"):
            expect(list_page_reset_button(page)).to_be_visible()
            expect(list_page_query_button(page)).to_be_visible()
            expect(list_page_expand_link(page)).to_be_visible()
            expect(list_page_create_button(page, "创建事件")).to_be_visible()
            expect(list_page_export_button(page)).to_be_visible()
            expect(list_page_pagination(page)).to_be_visible()

        with allure.step("点击'展开', 校验追加显示 8 项查询条件"):
            list_page_expand_link(page).click()
            for label_text in ["事件来源", "事件状态", "楼栋", "机柜影响",
                               "责任人", "创建人", "设备类型", "故障设备"]:
                expect(event_form_label(page, label_text)).to_be_visible(timeout=10000)

        with allure.step("点击'收起', 校验仅恢复展示 事件名称/事件类型/事件等级 三项"):
            expect(event_collapse_link(page)).to_be_visible()
            event_collapse_link(page).click()
            # 3 项基础查询条件恢复可见
            for label_text in ["事件名称", "事件类型", "事件等级"]:
                expect(event_form_label(page, label_text)).to_be_visible(timeout=10000)
            # 展开项恢复隐藏
            for hidden_label in ["事件来源", "事件状态", "楼栋", "机柜影响",
                                 "责任人", "创建人", "设备类型", "故障设备"]:
                expect(event_form_label(page, hidden_label)).not_to_be_visible()

        with allure.step("校验数据列表表头字段: 事件ID/事件名称/事件等级/故障位置/事件状态/操作"):
            header = event_table_header(page)
            expect(header).to_contain_text("事件ID")
            expect(header).to_contain_text("事件名称")
            expect(header).to_contain_text("事件等级")
            expect(header).to_contain_text("故障位置")
            expect(header).to_contain_text("事件状态")
            expect(header).to_contain_text("操作")

        with allure.step("横向滚动列表至最后, 校验右侧列: 故障原因/创建时间/责任人/创建人/关闭时间"):
            # 滚动容器为 ant-table-body, 表头随滚动同步
            event_table_body(page).evaluate("el => el.scrollLeft = el.scrollWidth")
            page.wait_for_load_state("networkidle")
            header2 = event_table_header(page)
            expect(header2).to_contain_text("故障原因")
            expect(header2).to_contain_text("创建时间")
            expect(header2).to_contain_text("责任人")
            expect(header2).to_contain_text("创建人")
            expect(header2).to_contain_text("关闭时间")
            # 滚动后校验右侧列已进入可视区域 (bounding box x 在视口内)
            for col in ["故障原因", "创建时间", "责任人", "创建人", "关闭时间"]:
                th = header2.locator("th", has_text=col).first
                expect(th).to_be_visible()
                box = th.bounding_box()
                assert box is not None and 0 <= box["x"] < 1800, \
                    f"横向滚动后列 {col!r} 未进入可视区域: box={box}"

        with allure.step("点击左侧菜单栏工作台, 返回工作台菜单栏, 校验工作台 Tab 选中"):
            workbench_menu_item(page).click()
            expect(page).to_have_url(re.compile(r"/dashboard"), timeout=15000)
            expect(tab_workbench(page)).to_have_attribute("aria-selected", "true", timeout=10000)
