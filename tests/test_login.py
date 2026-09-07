# -*- coding: utf-8 -*-
"""
观星系统 - Web 登录功能自动化测试
================================================================
技术栈: Python + Playwright + pytest + allure
被测地址: https://stargazer-test.mimiron.cn:8443/login

设计要点:
1. 账号密码通过环境变量注入, 不在代码中硬编码;
2. 元素定位优先使用 角色(role) / 文本(text) / id, 不使用硬编码 XPath;
3. 全程使用 Playwright 自动等待断言 (expect), 不使用 time.sleep;
4. 每个用例独立浏览器上下文 (function 级 context), 页面自动关闭;
5. 通过 @allure.feature / @allure.story 标记测试报告.
================================================================
"""

import os
import re

import pytest
import allure
from playwright.sync_api import sync_playwright, expect, Page


# ==================== 测试配置 (环境变量注入, 避免硬编码) ====================

# 被测登录页地址
BASE_URL = os.getenv(
    "LOGIN_BASE_URL",
    "https://stargazer-test.mimiron.cn:8443/login?redirect_to=%2Fevent%3Fcurrent%3D1%26pageSize%3D10",
)

# 登录账号: 用户名非敏感, 设默认值; 密码必须通过环境变量提供 (不写入代码)
LOGIN_USERNAME = os.getenv("LOGIN_USERNAME", "zhenyu_m")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "")  # 运行前: export LOGIN_PASSWORD='xxx'

# 错误密码 (用于"错误密码登录"用例, 非敏感)
WRONG_PASSWORD = os.getenv("WRONG_PASSWORD", "Wrong_Pwd@2026#")

# 登录成功后首页可见的"欢迎文本" (即登录用户在右上角显示的姓名)
EXPECTED_WELCOME_TEXT = os.getenv("EXPECTED_WELCOME_TEXT", "孟震宇")

# 错误密码登录后预期的错误提示文案 (以后台实际文案为准, 可用环境变量覆盖)
# 注: 实测错误密码登录后, 顶部 message toast 文案为 "用户名/密码不正确"
EXPECTED_LOGIN_ERROR_TEXT = os.getenv("EXPECTED_LOGIN_ERROR_TEXT", "用户名/密码不正确")

# 表单空值提交后的预期校验文案 (以后台实际文案为准, 可用环境变量覆盖)
# 注: 实测空用户名 toast 为 "请输入用户名!", 空密码 toast 为 "请输入密码!"
#     断言使用 to_contain_text 取核心子串, 不强依赖尾部标点
EXPECTED_EMPTY_USERNAME_ERROR = os.getenv("EXPECTED_EMPTY_USERNAME_ERROR", "请输入用户名")
EXPECTED_EMPTY_PASSWORD_ERROR = os.getenv("EXPECTED_EMPTY_PASSWORD_ERROR", "请输入密码")

# 是否无头模式运行
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"


# ==================== 元素定位器 (集中管理, 便于维护) ====================
# 说明: 该登录页基于 Ant Design, 输入框无 data-testid / aria-label,
#       但具备稳定的语义 id (#login / #password), 故采用 id 定位;
#       按钮采用 get_by_role + 文本正则 (兼容"登录"/"登 录"两种渲染).


def username_input(page: Page):
    """用户名输入框"""
    return page.locator("#login")


def password_input(page: Page):
    """密码输入框"""
    return page.locator("#password")


def login_button(page: Page):
    """登录按钮 (兼容 Ant Design 在两字按钮间插入空格的渲染方式)"""
    return page.get_by_role("button", name=re.compile(r"登\s*录"))


def error_toast(page: Page):
    """
    错误提示元素 (Ant Design message / notification / 内联表单错误).
    实测:
    - 错误密码登录失败 → 顶部 message toast ("用户名/密码不正确")
    - 空字段提交      → 内联表单错误 (.ant-form-item-explain-error)
    合并多种形态以兼容两种场景.
    """
    return page.locator(
        ".ant-message-notice, .ant-notification-notice, "
        ".ant-form-item-explain-error, .ant-form-item-explain, .ant-alert"
    ).last


def open_login_page(page: Page):
    """
    打开登录页并显式等待其完全就绪.
    关键: 必须用 wait_until="networkidle" 等待 SPA 完成异步初始化,
          否则 Ant Design ProForm 字段尚未注册, fill 写入的值会被表单重置.
    """
    page.goto(BASE_URL, wait_until="networkidle")
    # 等待输入框不仅可见, 且可编辑 (SPA 异步初始化可能延迟注册表单字段)
    expect(username_input(page)).to_be_visible()
    expect(username_input(page)).to_be_editable()


# ==================== pytest fixture: 浏览器上下文管理 ====================


@pytest.fixture(scope="session")
def playwright():
    """启动 Playwright 驱动 (整个会话只启动一次)"""
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright):
    """启动 Chromium 浏览器实例 (会话级)"""
    # headless 模式下页面可能崩溃, 需附加启动参数提升稳定性
    launch_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-setuid-sandbox",
    ]
    browser = playwright.chromium.launch(headless=HEADLESS, args=launch_args)
    yield browser
    browser.close()


@pytest.fixture(scope="function")
def context(browser):
    """
    每个用例独立创建一个浏览器上下文 (隔离 cookie / session),
    保证用例之间互不影响; 用例结束自动关闭.
    ignore_https_errors: 测试环境 (8443) 可能使用自签名证书, 予以忽略.
    locale=zh-CN: 系统按 navigator.language 决定界面语言,
                  设为中文以匹配中文断言文案 (如"登 录"/"请输入"等).
    """
    context = browser.new_context(ignore_https_errors=True, locale="zh-CN")
    yield context
    context.close()


@pytest.fixture(scope="function")
def page(context, request):
    """
    每个用例独立创建一个页面, 用例结束自动关闭;
    并在结束时附加页面截图到 allure 报告, 便于失败排查.
    """
    page = context.new_page()
    # 设置默认自动等待超时 (测试环境响应可能较慢)
    page.set_default_timeout(15000)
    yield page
    # 用例结束后附加截图 (无论成功失败均记录最终页面状态)
    try:
        allure.attach(
            page.screenshot(),
            name=f"页面快照-{request.node.name}",
            attachment_type=allure.attachment_type.PNG,
        )
    except Exception:
        pass
    page.close()


# ==================== 测试用例 ====================


@allure.feature("登录功能")
@allure.label("owner", "自动化测试")
@allure.link("https://stargazer-test.mimiron.cn:8443/login", name="被测登录页")
class TestLogin:
    """观星系统登录功能测试"""

    # ---------- 1. 正常登录 ----------

    @allure.story("正常账号密码登录")
    @allure.title("正常登录成功并跳转首页, 校验欢迎文本")
    @allure.severity(allure.severity_level.BLOCKER)
    def test_login_success(self, page: Page):
        # 前置校验: 密码必须通过环境变量提供
        if not LOGIN_PASSWORD:
            pytest.skip("未设置环境变量 LOGIN_PASSWORD, 跳过正常登录用例")

        with allure.step("打开登录页 (等待 SPA 完全就绪)"):
            open_login_page(page)

        with allure.step("输入正确的用户名和密码"):
            # 先 click 聚焦再 fill, 防止 SPA 表单重置导致写入被清空;
            # fill 后立即断言 value 已写入, 快速定位偶发问题
            username_input(page).click()
            username_input(page).fill(LOGIN_USERNAME)
            expect(username_input(page)).to_have_value(LOGIN_USERNAME)
            password_input(page).click()
            password_input(page).fill(LOGIN_PASSWORD)
            expect(password_input(page)).to_have_value(LOGIN_PASSWORD)

        with allure.step("点击登录按钮并等待跳转首页"):
            login_button(page).click()
            # 显式等待: 登录成功后 URL 应跳转到 /event
            # (登录页 URL 含编码后的 %2Fevent, 正则 /event 不会误匹配)
            expect(page).to_have_url(re.compile(r"/event"), timeout=15000)

        with allure.step("校验首页欢迎文本 (登录用户姓名) 可见"):
            expect(page.get_by_text(EXPECTED_WELCOME_TEXT).first).to_be_visible()

    # ---------- 2. 错误密码登录 ----------

    @allure.story("错误密码登录")
    @allure.title("错误密码登录失败, 校验错误提示文案出现")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_login_wrong_password(self, page: Page):
        with allure.step("打开登录页 (等待 SPA 完全就绪)"):
            open_login_page(page)

        with allure.step("输入正确用户名 + 错误密码"):
            username_input(page).fill(LOGIN_USERNAME)
            password_input(page).fill(WRONG_PASSWORD)

        with allure.step("点击登录按钮"):
            login_button(page).click()

        with allure.step("校验: 仍在登录页 (未发生跳转)"):
            # 显式等待: URL 仍停留在 /login, 说明登录未成功
            expect(page).to_have_url(re.compile(r"/login"), timeout=10000)

        with allure.step("校验: 顶部错误提示 toast 出现且文案正确"):
            # 实测: 错误密码登录失败时, 通过 Ant Design 顶部 message toast 提示
            toast = error_toast(page)
            expect(toast).to_be_visible(timeout=10000)
            expect(toast).to_contain_text(EXPECTED_LOGIN_ERROR_TEXT)

    # ---------- 3. 空用户名提交 ----------

    @allure.story("空用户名提交")
    @allure.title("用户名为空时提交, 校验表单校验提示")
    @allure.severity(allure.severity_level.NORMAL)
    def test_login_empty_username(self, page: Page):
        with allure.step("打开登录页 (等待 SPA 完全就绪)"):
            open_login_page(page)

        with allure.step("仅填写密码, 用户名留空"):
            # 用户名输入框保持为空
            password_input(page).fill(WRONG_PASSWORD)

        with allure.step("点击登录按钮触发表单校验"):
            login_button(page).click()

        with allure.step("校验: 用户名校验提示 toast 出现且文案正确"):
            # 实测: 空用户名提交时, 顶部 message toast 提示 "请输入用户名!"
            toast = error_toast(page)
            expect(toast).to_be_visible(timeout=10000)
            expect(toast).to_contain_text(EXPECTED_EMPTY_USERNAME_ERROR)

        with allure.step("校验: 仍在登录页 (未发生跳转)"):
            expect(page).to_have_url(re.compile(r"/login"), timeout=5000)

    # ---------- 4. 空密码提交 ----------

    @allure.story("空密码提交")
    @allure.title("密码为空时提交, 校验表单校验提示")
    @allure.severity(allure.severity_level.NORMAL)
    def test_login_empty_password(self, page: Page):
        with allure.step("打开登录页 (等待 SPA 完全就绪)"):
            open_login_page(page)

        with allure.step("仅填写用户名, 密码留空"):
            username_input(page).fill(LOGIN_USERNAME)
            # 密码输入框保持为空

        with allure.step("点击登录按钮触发表单校验"):
            login_button(page).click()

        with allure.step("校验: 密码校验提示 toast 出现且文案正确"):
            # 实测: 空密码提交时, 顶部 message toast 提示 "请输入密码!"
            toast = error_toast(page)
            expect(toast).to_be_visible(timeout=10000)
            expect(toast).to_contain_text(EXPECTED_EMPTY_PASSWORD_ERROR)

        with allure.step("校验: 仍在登录页 (未发生跳转)"):
            expect(page).to_have_url(re.compile(r"/login"), timeout=5000)
