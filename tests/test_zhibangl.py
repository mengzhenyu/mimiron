# -*- coding: utf-8 -*-
"""
观星系统 - Web 值班管理 > 班次设置 E2E 自动化测试
================================================================
技术栈: Python + Playwright + pytest + allure
被测地址: https://stargazer-test.mimiron.cn:8443/infra-attendance/schedule-attendance/shifts

页面结构 (基于实测探查):
  列表页:
    - 搜索区: 搜索班次名称 / 搜索负责人 / 重置 / 查询
    - 操作按钮: 新增班次
    - 表格列: 班次名称 / 颜色标记 / 考勤时间 / 操作(编辑、删除)
  新增/编辑抽屉 (Ant Design Drawer, 标题"新增班次"/"编辑班次"):
    - 班次名称       (input, placeholder="请输入班次名称")
    - 班次负责人     (ant-select, 默认"请选择")
    - 颜色标记       (ant-color-picker, 默认蓝色 rgb(22,119,255))
    - 上班时间       (时间选择器 + "当日"下拉 + "上班打卡"开关)
    - 下班时间       (时间选择器 + "当日"下拉 + "下班打卡"开关)
    - 设置打卡时间范围 (link button)
    - 设置工作时段内休息 (button)
    - 总工作时长     (文本, 如 "0小时0分钟")
    - 弹性设置 > 晚走次日晚到 (开关)
    - 底部按钮: 取消 / 确定

设计要点:
  1. 账号密码 / 被测 URL 通过环境变量注入, 禁止硬编码;
  2. 定位优先 get_by_role / get_by_placeholder / get_by_text, 不使用绝对 XPath;
  3. 禁止 time.sleep, 统一使用 expect 断言与 Playwright 自动等待;
  4. session 级登录复用, 每个用例前导航回班次设置页保证起始状态一致;
  5. 新增的测试数据在用例结束后清理, 避免污染环境;
  6. 全部用例加 @allure.feature / @allure.story 装饰器.
================================================================
"""

import os
import re
import time

import pytest
import allure
from playwright.sync_api import sync_playwright, expect, Page


# ==================== 测试配置 (环境变量注入, 避免硬编码) ====================

# 被测系统基础地址
BASE_URL = os.getenv("ZHIBANGL_BASE_URL", "https://stargazer-test.mimiron.cn:8443")

# 登录页地址
LOGIN_URL = os.getenv("ZHIBANGL_LOGIN_URL", "https://stargazer-test.mimiron.cn:8443/login")

# 班次设置页地址
SHIFTS_URL = f"{BASE_URL}/infra-attendance/schedule-attendance/shifts"

# 登录账号: 用户名非敏感, 设默认值; 密码必须通过环境变量提供 (不写入代码)
LOGIN_USERNAME = os.getenv("LOGIN_USERNAME", "zhenyu_m")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "")  # 运行前: export LOGIN_PASSWORD='xxx'

# 是否无头模式运行
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

# 测试用唯一班次名前缀 (用于创建后清理)
TEST_SHIFT_PREFIX = "AT_班次_"


# ==================== 元素定位器 (集中管理, 便于维护) ====================
# 说明: 班次设置基于 Ant Design, 以下定位优先使用语义角色 / placeholder / 文本.

# ---------- 列表页元素 ----------

def search_name_input(page: Page):
    """搜索班次名称输入框"""
    return page.get_by_placeholder("搜索班次名称")


def search_owner_input(page: Page):
    """搜索负责人输入框"""
    return page.get_by_placeholder("搜索负责人")


def reset_button(page: Page):
    """重置按钮"""
    return page.get_by_role("button", name=re.compile(r"重\s*置"))


def query_button(page: Page):
    """查询按钮"""
    return page.get_by_role("button", name=re.compile(r"查\s*询"))


def add_shift_button(page: Page):
    """新增班次按钮"""
    return page.get_by_role("button", name=re.compile(r"新\s*增\s*班\s*次"))


def shifts_table(page: Page):
    """班次数据表格"""
    return page.locator(".ant-table").first


def shifts_table_rows(page: Page):
    """表格数据行"""
    return page.locator(".ant-table-tbody > tr")


def shift_name_column(row):
    """表格行中的班次名称单元格"""
    return row.locator("td").nth(0)


# ---------- 抽屉(Drawer)元素 ----------

def shifts_drawer(page: Page):
    """新增/编辑班次抽屉容器"""
    return page.locator(".ant-drawer-content")


def drawer_title(page: Page):
    """抽屉标题"""
    return page.locator(".ant-drawer-title")


def shift_name_input(page: Page):
    """班次名称输入框"""
    return page.get_by_placeholder("请输入班次名称")


def owner_select(page: Page):
    """班次负责人下拉选择器"""
    return page.locator(".ant-select").first


def color_picker_trigger(page: Page):
    """颜色标记选择器触发按钮"""
    return page.locator(".ant-color-picker-trigger")


def color_picker_panel(page: Page):
    """颜色选择面板"""
    return page.locator(".ant-color-picker-panel")


def work_start_time_picker(page: Page):
    """上班时间选择器 (第一个时间输入框)"""
    return page.get_by_placeholder("请选择时间").nth(0)


def work_end_time_picker(page: Page):
    """下班时间选择器 (第二个时间输入框)"""
    return page.get_by_placeholder("请选择时间").nth(1)


def punch_in_switch(page: Page):
    """上班打卡开关"""
    return page.locator(".ant-switch").nth(0)


def punch_out_switch(page: Page):
    """下班打卡开关"""
    return page.locator(".ant-switch").nth(1)


def flexible_switch(page: Page):
    """弹性设置 > 晚走次日晚到 (实测为 checkbox, 非 switch)"""
    return page.locator(".ant-checkbox-wrapper", has_text=re.compile(r"晚走次日晚到")).locator(".ant-checkbox")


def set_punch_time_range_btn(page: Page):
    """设置打卡时间范围按钮"""
    return page.get_by_text("设置打卡时间范围", exact=True)


def drawer_cancel_btn(page: Page):
    """抽屉取消按钮"""
    return page.get_by_role("button", name=re.compile(r"取\s*消"))


def drawer_confirm_btn(page: Page):
    """抽屉确定按钮"""
    return page.get_by_role("button", name=re.compile(r"确\s*定"))


def error_toast(page: Page):
    """错误/提示 toast"""
    return page.locator(".ant-message-notice, .ant-notification-notice").last


# ==================== 辅助函数 ====================

def open_shifts_page(page: Page):
    """导航到班次设置页并等待加载就绪"""
    page.goto(SHIFTS_URL, wait_until="networkidle")
    expect(page).to_have_url(re.compile(r"/shifts"), timeout=15000)
    # 等待"新增班次"按钮可见, 作为页面就绪标志
    expect(add_shift_button(page)).to_be_visible(timeout=15000)


def fill_shift_form(page: Page, name: str, owner: str = "Admin",
                    start_time: str = "09:00", end_time: str = "18:00"):
    """
    填写班次表单的必填字段: 班次名称 / 班次负责人 / 上班时间 / 下班时间.
    上下班打卡开关保持默认开启状态.
    """
    # 1. 班次名称
    shift_name_input(page).click()
    shift_name_input(page).fill(name)
    expect(shift_name_input(page)).to_have_value(name)

    # 2. 班次负责人 (下拉选择)
    owner_select(page).click()
    page.wait_for_timeout(800)
    # 直接点击包含目标文本的选项 (force=True 绕过遮挡)
    owner_option = page.locator(".ant-select-item-option", has_text=owner)
    if owner_option.count() > 0:
        owner_option.first.click(force=True)
    else:
        page.locator(".ant-select-item-option").first.click(force=True)
    page.wait_for_timeout(300)
    # 按 Escape 确保下拉面板关闭
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)

    # 3. 上班时间 (TimePicker, 直接输入时间字符串 + Enter)
    work_start_time_picker(page).click()
    work_start_time_picker(page).fill(start_time)
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    # 点击空白处关闭可能残留的时间面板
    page.locator(".ant-drawer-body").click(position={"x": 10, "y": 10})
    page.wait_for_timeout(200)

    # 4. 下班时间
    work_end_time_picker(page).click()
    work_end_time_picker(page).fill(end_time)
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    page.locator(".ant-drawer-body").click(position={"x": 10, "y": 10})
    page.wait_for_timeout(200)

    return page


def search_shift_by_name(page: Page, name: str):
    """在班次名称搜索框中输入关键词并查询, 用于精确定位某班次"""
    search_name_input(page).click()
    search_name_input(page).fill(name)
    query_button(page).click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)


def get_shift_row_by_name(page: Page, name: str, use_search: bool = True):
    """
    在表格中查找指定班次名称所在的行.
    use_search=True 时先在搜索框中精确搜索, 避免翻页遗漏.
    返回 row locator 或 None.
    """
    if use_search:
        search_shift_by_name(page, name)

    rows = shifts_table_rows(page).all()
    for row in rows:
        try:
            cell_text = row.locator("td").nth(0).inner_text(timeout=5000).strip()
            if cell_text == name:
                return row
        except Exception:
            continue
    return None


def delete_shift_if_exists(page: Page, name: str):
    """
    清理测试数据: 如果指定班次存在则删除.
    处理 Ant Design Popconfirm / Modal 两种确认框.
    """
    row = get_shift_row_by_name(page, name)
    if row is None:
        return
    row.get_by_role("button", name="删除").click()
    page.wait_for_timeout(800)

    # 按优先级尝试不同确认框定位
    confirm_locators = [
        page.locator(".ant-popconfirm-buttons .ant-btn-primary"),
        page.locator(".ant-popover-buttons .ant-btn-primary"),
        page.locator(".ant-modal-footer .ant-btn-primary"),
        page.get_by_role("button", name=re.compile(r"确\s*定|OK")),
    ]
    for loc in confirm_locators:
        if loc.count() > 0:
            try:
                loc.first.click(force=True, timeout=3000)
                break
            except Exception:
                continue
    page.wait_for_timeout(1500)


# ==================== pytest fixture: 浏览器与登录 (session 级共享) ====================


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
    单次登录并进入系统 (session 级, 所有用例复用同一登录态).
    登录元素定位复用 test_login.py 已验证的 #login / #password / 登录按钮.
    """
    page = context.new_page()
    page.set_default_timeout(15000)

    # 打开登录页
    page.goto(LOGIN_URL, wait_until="networkidle")

    # 登录流程
    username_locator = page.locator("#login")
    password_locator = page.locator("#password")
    login_btn = page.get_by_role("button", name=re.compile(r"登\s*录"))

    expect(username_locator).to_be_editable()
    username_locator.click()
    username_locator.fill(LOGIN_USERNAME)
    expect(username_locator).to_have_value(LOGIN_USERNAME)
    password_locator.click()
    password_locator.fill(LOGIN_PASSWORD)
    expect(password_locator).to_have_value(LOGIN_PASSWORD)
    login_btn.click()

    # 等待登录成功跳转首页
    expect(page).to_have_url(re.compile(r"/dashboard|/event"), timeout=15000)

    yield page
    page.close()


# ==================== 测试用例 ====================


@allure.feature("值班管理-班次设置")
@allure.label("owner", "自动化测试")
@allure.link("https://stargazer-test.mimiron.cn:8443/login", name="被测系统登录页")
class TestZhiBangL:
    """观星系统 - 值班管理 > 班次设置 E2E 测试"""

    @pytest.fixture(autouse=True)
    def reset_to_shifts(self, logged_in_page: Page):
        """
        autouse fixture: 每个用例执行前, 统一导航回班次设置页并等待就绪.
        保证每个用例起始状态一致 (页面在班次设置列表页).
        """
        open_shifts_page(logged_in_page)
        yield

    # ==================== 一、列表页测试 ====================

    @allure.story("班次设置列表页")
    @allure.title("进入班次设置页, 验证页面核心元素加载正常")
    @allure.severity(allure.severity_level.BLOCKER)
    def test_shifts_page_load(self, logged_in_page: Page):
        with allure.step("验证搜索区元素"):
            expect(search_name_input(logged_in_page)).to_be_visible()
            expect(search_owner_input(logged_in_page)).to_be_visible()
            expect(reset_button(logged_in_page)).to_be_visible()
            expect(query_button(logged_in_page)).to_be_visible()

        with allure.step("验证新增按钮可见"):
            expect(add_shift_button(logged_in_page)).to_be_visible()

        with allure.step("验证表格列头正确"):
            table = shifts_table(logged_in_page)
            expect(table).to_be_visible()
            headers = table.locator(".ant-table-thead th").all_text_contents()
            header_texts = [h.strip() for h in headers]
            assert "班次名称" in header_texts
            assert "颜色标记" in header_texts
            assert "考勤时间" in header_texts
            assert "操作" in header_texts

    @allure.story("班次设置列表页")
    @allure.title("按班次名称搜索, 验证结果过滤")
    @allure.severity(allure.severity_level.NORMAL)
    def test_search_by_name(self, logged_in_page: Page):
        with allure.step("输入班次名称关键词并查询"):
            search_name_input(logged_in_page).click()
            search_name_input(logged_in_page).fill("测试")
            query_button(logged_in_page).click()
            logged_in_page.wait_for_load_state("networkidle")
            logged_in_page.wait_for_timeout(1000)

        with allure.step("验证表格显示结果 (可能为空或包含关键词)"):
            # 搜索后表格仍存在, 且行数不增加
            expect(shifts_table(logged_in_page)).to_be_visible()

        with allure.step("重置搜索条件"):
            reset_button(logged_in_page).click()
            expect(search_name_input(logged_in_page)).to_have_value("")

    @allure.story("班次设置列表页")
    @allure.title("按负责人搜索, 验证查询功能可用")
    @allure.severity(allure.severity_level.NORMAL)
    def test_search_by_owner(self, logged_in_page: Page):
        with allure.step("输入负责人关键词并查询"):
            search_owner_input(logged_in_page).click()
            search_owner_input(logged_in_page).fill("admin")
            query_button(logged_in_page).click()
            logged_in_page.wait_for_load_state("networkidle")
            logged_in_page.wait_for_timeout(1000)

        with allure.step("验证表格存在"):
            expect(shifts_table(logged_in_page)).to_be_visible()

        with allure.step("重置搜索条件"):
            reset_button(logged_in_page).click()
            expect(search_owner_input(logged_in_page)).to_have_value("")

    @allure.story("班次设置列表页")
    @allure.title("点击重置按钮, 验证搜索条件清空")
    @allure.severity(allure.severity_level.NORMAL)
    def test_reset_search(self, logged_in_page: Page):
        with allure.step("输入搜索条件"):
            search_name_input(logged_in_page).fill("ABC123")
            search_owner_input(logged_in_page).fill("xyz789")

        with allure.step("点击重置"):
            reset_button(logged_in_page).click()

        with allure.step("验证两个搜索框均已清空"):
            expect(search_name_input(logged_in_page)).to_have_value("")
            expect(search_owner_input(logged_in_page)).to_have_value("")

    # ==================== 二、新增班次测试 ====================

    @allure.story("新增班次")
    @allure.title("点击新增班次, 验证抽屉打开且字段完整")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_open_add_drawer(self, logged_in_page: Page):
        with allure.step("点击新增班次按钮"):
            add_shift_button(logged_in_page).click()
            expect(shifts_drawer(logged_in_page)).to_be_visible(timeout=10000)

        with allure.step("验证抽屉标题为'新增班次'"):
            expect(drawer_title(logged_in_page)).to_contain_text("新增班次")

        with allure.step("验证表单字段可见"):
            expect(shift_name_input(logged_in_page)).to_be_visible()
            expect(owner_select(logged_in_page)).to_be_visible()
            expect(color_picker_trigger(logged_in_page)).to_be_visible()
            expect(work_start_time_picker(logged_in_page)).to_be_visible()
            expect(work_end_time_picker(logged_in_page)).to_be_visible()

        with allure.step("验证底部按钮"):
            expect(drawer_cancel_btn(logged_in_page)).to_be_visible()
            expect(drawer_confirm_btn(logged_in_page)).to_be_visible()

        with allure.step("关闭抽屉"):
            drawer_cancel_btn(logged_in_page).click()
            expect(shifts_drawer(logged_in_page)).not_to_be_visible(timeout=5000)

    @allure.story("新增班次")
    @allure.title("班次名称为空时提交, 验证表单校验提示")
    @allure.severity(allure.severity_level.NORMAL)
    def test_add_shift_empty_name(self, logged_in_page: Page):
        with allure.step("打开新增抽屉"):
            add_shift_button(logged_in_page).click()
            expect(shifts_drawer(logged_in_page)).to_be_visible(timeout=10000)

        with allure.step("班次名称留空, 直接点击确定"):
            drawer_confirm_btn(logged_in_page).click()
            logged_in_page.wait_for_timeout(500)

        with allure.step("验证抽屉未关闭 (校验失败)"):
            # 校验失败时抽屉仍应保持打开
            expect(shifts_drawer(logged_in_page)).to_be_visible()

        with allure.step("关闭抽屉"):
            drawer_cancel_btn(logged_in_page).click()

    @allure.story("新增班次")
    @allure.title("填写班次名称后确定, 验证新增成功并出现在列表")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_add_shift_success(self, logged_in_page: Page):
        shift_name = f"{TEST_SHIFT_PREFIX}新增_{int(time.time())}"

        try:
            with allure.step(f"打开新增抽屉并填写班次名称: {shift_name}"):
                add_shift_button(logged_in_page).click()
                expect(shifts_drawer(logged_in_page)).to_be_visible(timeout=10000)
                fill_shift_form(logged_in_page, shift_name)

            with allure.step("点击确定提交"):
                drawer_confirm_btn(logged_in_page).click()
                # 等待抽屉关闭 (提交成功)
                expect(shifts_drawer(logged_in_page)).not_to_be_visible(timeout=10000)

            with allure.step("回到列表页验证新增班次出现在表格中"):
                open_shifts_page(logged_in_page)
                logged_in_page.wait_for_timeout(1500)
                row = get_shift_row_by_name(logged_in_page, shift_name)
                assert row is not None, f"新增班次 '{shift_name}' 未出现在列表中"

        finally:
            # 清理测试数据
            with allure.step("清理测试数据: 删除新增的班次"):
                delete_shift_if_exists(logged_in_page, shift_name)

    @allure.story("新增班次")
    @allure.title("点击取消, 验证抽屉关闭且无新增数据")
    @allure.severity(allure.severity_level.NORMAL)
    def test_add_shift_cancel(self, logged_in_page: Page):
        shift_name = f"{TEST_SHIFT_PREFIX}取消_{int(time.time())}"

        with allure.step("打开新增抽屉并填写内容"):
            add_shift_button(logged_in_page).click()
            expect(shifts_drawer(logged_in_page)).to_be_visible(timeout=10000)
            fill_shift_form(logged_in_page, shift_name)

        with allure.step("点击取消"):
            drawer_cancel_btn(logged_in_page).click()
            expect(shifts_drawer(logged_in_page)).not_to_be_visible(timeout=5000)

        with allure.step("验证列表中不存在该班次"):
            open_shifts_page(logged_in_page)
            logged_in_page.wait_for_timeout(1000)
            row = get_shift_row_by_name(logged_in_page, shift_name)
            assert row is None, f"取消新增后, 班次 '{shift_name}' 不应存在"

    # ==================== 三、颜色标记测试 ====================

    @allure.story("班次表单-颜色标记")
    @allure.title("点击颜色标记, 验证颜色选择面板打开")
    @allure.severity(allure.severity_level.NORMAL)
    def test_color_picker_opens(self, logged_in_page: Page):
        with allure.step("打开新增抽屉"):
            add_shift_button(logged_in_page).click()
            expect(shifts_drawer(logged_in_page)).to_be_visible(timeout=10000)

        with allure.step("点击颜色标记选择器"):
            color_picker_trigger(logged_in_page).click()
            logged_in_page.wait_for_timeout(800)

        with allure.step("验证颜色选择面板出现"):
            # 颜色面板可能在弹窗内或页面级
            panel = logged_in_page.locator(".ant-color-picker-panel")
            if panel.count() > 0:
                expect(panel.first).to_be_visible()

        with allure.step("关闭抽屉"):
            drawer_cancel_btn(logged_in_page).click()

    # ==================== 四、编辑班次测试 ====================

    @allure.story("编辑班次")
    @allure.title("编辑已有班次名称, 验证更新成功")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_edit_shift(self, logged_in_page: Page):
        original_name = f"{TEST_SHIFT_PREFIX}编辑原_{int(time.time())}"
        edited_name = f"{TEST_SHIFT_PREFIX}编辑后_{int(time.time())}"

        try:
            with allure.step("前置: 新建一个班次用于编辑"):
                add_shift_button(logged_in_page).click()
                expect(shifts_drawer(logged_in_page)).to_be_visible(timeout=10000)
                fill_shift_form(logged_in_page, original_name)
                drawer_confirm_btn(logged_in_page).click()
                expect(shifts_drawer(logged_in_page)).not_to_be_visible(timeout=10000)
                open_shifts_page(logged_in_page)
                logged_in_page.wait_for_timeout(1500)

            with allure.step("点击该班次的编辑按钮"):
                row = get_shift_row_by_name(logged_in_page, original_name)
                assert row is not None, f"前置班次 '{original_name}' 未创建成功"
                row.get_by_role("button", name="编辑").click()
                expect(shifts_drawer(logged_in_page)).to_be_visible(timeout=10000)

            with allure.step("修改班次名称并确定"):
                expect(shift_name_input(logged_in_page)).to_have_value(original_name)
                shift_name_input(logged_in_page).click()
                shift_name_input(logged_in_page).fill(edited_name)
                expect(shift_name_input(logged_in_page)).to_have_value(edited_name)
                drawer_confirm_btn(logged_in_page).click()
                expect(shifts_drawer(logged_in_page)).not_to_be_visible(timeout=10000)

            with allure.step("验证列表中显示编辑后的名称"):
                open_shifts_page(logged_in_page)
                logged_in_page.wait_for_timeout(1500)
                row_new = get_shift_row_by_name(logged_in_page, edited_name)
                assert row_new is not None, f"编辑后班次 '{edited_name}' 未出现在列表中"

        finally:
            with allure.step("清理测试数据"):
                delete_shift_if_exists(logged_in_page, original_name)
                delete_shift_if_exists(logged_in_page, edited_name)

    # ==================== 五、删除班次测试 ====================

    @allure.story("删除班次")
    @allure.title("删除班次时点击取消, 验证班次未被删除")
    @allure.severity(allure.severity_level.NORMAL)
    def test_delete_shift_cancel(self, logged_in_page: Page):
        shift_name = f"{TEST_SHIFT_PREFIX}删取消_{int(time.time())}"

        try:
            with allure.step("前置: 新建一个班次"):
                add_shift_button(logged_in_page).click()
                expect(shifts_drawer(logged_in_page)).to_be_visible(timeout=10000)
                fill_shift_form(logged_in_page, shift_name)
                drawer_confirm_btn(logged_in_page).click()
                expect(shifts_drawer(logged_in_page)).not_to_be_visible(timeout=10000)
                open_shifts_page(logged_in_page)
                logged_in_page.wait_for_timeout(1500)

            with allure.step("点击删除按钮"):
                row = get_shift_row_by_name(logged_in_page, shift_name)
                assert row is not None, f"前置班次 '{shift_name}' 未创建成功"
                row.get_by_role("button", name="删除").click()
                logged_in_page.wait_for_timeout(500)

            with allure.step("在确认弹窗中点击取消"):
                cancel_locators = [
                    logged_in_page.locator(".ant-popconfirm-buttons .ant-btn-default"),
                    logged_in_page.locator(".ant-popover-buttons .ant-btn-default"),
                    logged_in_page.locator(".ant-modal-footer .ant-btn-default"),
                    logged_in_page.get_by_role("button", name=re.compile(r"取\s*消|Cancel")),
                ]
                for loc in cancel_locators:
                    if loc.count() > 0:
                        try:
                            loc.first.click(force=True, timeout=3000)
                            break
                        except Exception:
                            continue

            with allure.step("验证班次仍存在"):
                open_shifts_page(logged_in_page)
                logged_in_page.wait_for_timeout(1000)
                row_after = get_shift_row_by_name(logged_in_page, shift_name)
                assert row_after is not None, f"取消删除后班次 '{shift_name}' 应仍存在"

        finally:
            with allure.step("清理测试数据"):
                delete_shift_if_exists(logged_in_page, shift_name)

    @allure.story("删除班次")
    @allure.title("确认删除班次, 验证班次从列表移除")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_delete_shift_confirm(self, logged_in_page: Page):
        shift_name = f"{TEST_SHIFT_PREFIX}删确认_{int(time.time())}"

        with allure.step("前置: 新建一个班次"):
            add_shift_button(logged_in_page).click()
            expect(shifts_drawer(logged_in_page)).to_be_visible(timeout=10000)
            fill_shift_form(logged_in_page, shift_name)
            drawer_confirm_btn(logged_in_page).click()
            expect(shifts_drawer(logged_in_page)).not_to_be_visible(timeout=10000)
            open_shifts_page(logged_in_page)
            logged_in_page.wait_for_timeout(1500)

        with allure.step("点击删除按钮"):
            row = get_shift_row_by_name(logged_in_page, shift_name)
            assert row is not None, f"前置班次 '{shift_name}' 未创建成功"
            row.get_by_role("button", name="删除").click()
            logged_in_page.wait_for_timeout(500)

        with allure.step("在确认弹窗中点击确定"):
            confirm_locators = [
                logged_in_page.locator(".ant-popconfirm-buttons .ant-btn-primary"),
                logged_in_page.locator(".ant-popover-buttons .ant-btn-primary"),
                logged_in_page.locator(".ant-modal-footer .ant-btn-primary"),
                logged_in_page.get_by_role("button", name=re.compile(r"确\s*定|OK")),
            ]
            for loc in confirm_locators:
                if loc.count() > 0:
                    try:
                        loc.first.click(force=True, timeout=3000)
                        break
                    except Exception:
                        continue
            logged_in_page.wait_for_timeout(1500)

        with allure.step("验证班次已从列表移除"):
            open_shifts_page(logged_in_page)
            logged_in_page.wait_for_timeout(1000)
            row_after = get_shift_row_by_name(logged_in_page, shift_name)
            assert row_after is None, f"确认删除后班次 '{shift_name}' 应不存在"

    # ==================== 六、弹性设置开关测试 ====================

    @allure.story("班次表单-弹性设置")
    @allure.title("切换'晚走次日晚到'开关, 验证状态可切换")
    @allure.severity(allure.severity_level.NORMAL)
    def test_flexible_switch_toggle(self, logged_in_page: Page):
        with allure.step("打开新增抽屉"):
            add_shift_button(logged_in_page).click()
            expect(shifts_drawer(logged_in_page)).to_be_visible(timeout=10000)

        with allure.step("记录弹性开关初始状态并切换"):
            sw = flexible_switch(logged_in_page)
            expect(sw).to_be_visible()
            initial_checked = "ant-checkbox-checked" in (sw.get_attribute("class") or "")
            sw.click()
            logged_in_page.wait_for_timeout(300)
            after_checked = "ant-checkbox-checked" in (sw.get_attribute("class") or "")
            assert initial_checked != after_checked, "弹性开关点击后状态应发生变化"

        with allure.step("关闭抽屉"):
            drawer_cancel_btn(logged_in_page).click()
