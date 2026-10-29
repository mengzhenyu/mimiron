# -*- coding: utf-8 -*-
"""
观星系统 - 值班管理 > 班组设置 E2E 自动化测试
================================================================
技术栈: Python + Playwright + pytest + allure
被测地址: https://stargazer-test.mimiron.cn:8443/infra-attendance/schedule-attendance/teams

页面结构 (基于实测探查):
  列表页:
    - 搜索区: 人员姓名输入框 (id=userName, placeholder="人员姓名") / 重置 / 查询
    - 操作按钮: 新建班组
    - 表格列: 班组名称 / 楼栋 / 关联人数 / 操作(编辑、删除)
    - 关联人数列可点击, 弹出"人员信息"弹窗 (人员工号 / 人员姓名)
    - 分页: 默认 10 条/页, 文案 "第 1-10 条/总共 N 条"
  新建/编辑抽屉 (Ant Design Drawer, 标题"新建班组"/"编辑班组"):
    - 班组名称   (input #teamName, placeholder="请输入班组名称", 必填)
    - 楼栋       (ant-cascader, placeholder="请选择楼栋", 必填; 选项: 园区楼/1号楼/2号楼/6号测试楼/5号-测试楼)
    - 班组成员   (ant-select multiple, placeholder="请选择班组成员", 必填)
    - 底部按钮: 取消 / 确定
  删除: Popconfirm "确认删除该班组？" + 取消 / 确定

设计要点:
  1. 账号密码 / 被测 URL 通过环境变量注入, 禁止硬编码;
  2. 定位优先 get_by_role / get_by_placeholder / id, 不使用绝对 XPath;
  3. 禁止 time.sleep, 统一使用 expect 断言与 Playwright 自动等待;
  4. session 级登录复用, 每个用例前导航回班组设置页保证起始状态一致;
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

BASE_URL = os.getenv("BANZU_BASE_URL", "https://stargazer-test.mimiron.cn:8443")
LOGIN_URL = os.getenv("BANZU_LOGIN_URL", "https://stargazer-test.mimiron.cn:8443/login")
TEAMS_BASE_URL = f"{BASE_URL}/infra-attendance/schedule-attendance/teams"

LOGIN_USERNAME = os.getenv("LOGIN_USERNAME", "zhenyu_m")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "")  # 取值为 .env 中的 LOGIN_PASSWORD (conftest.py 自动加载)

HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

# 测试数据前缀, 便于创建后清理
TEST_TEAM_PREFIX = "AT_班组_"

# 保留班组前缀: 每次运行结束后保留一个, 供 test_kaoqin 优先使用 (空闲班组);
# 下次运行时先删除上次保留的, 运行结束后再保留一个新的
RETAINED_TEAM_PREFIX = "AT_班组_保留_"


# ==================== 元素定位器 (集中管理, 便于维护) ====================

# ---------- 列表页元素 ----------

def search_input(page: Page):
    """搜索区 - 人员姓名输入框"""
    return page.locator("#userName")


def reset_button(page: Page):
    """重置按钮"""
    return page.get_by_role("button", name=re.compile(r"重\s*置"))


def query_button(page: Page):
    """查询按钮"""
    return page.get_by_role("button", name=re.compile(r"查\s*询"))


def add_team_button(page: Page):
    """新建班组按钮"""
    return page.get_by_role("button", name=re.compile(r"新\s*建\s*班\s*组"))


def team_rows(page: Page):
    """表格数据行 (排除 measure-row)"""
    return page.locator(".ant-table-tbody > tr.ant-table-row")


def pagination(page: Page):
    """分页组件"""
    return page.locator(".ant-pagination").first


def empty_placeholder(page: Page):
    """表格空数据提示"""
    return page.locator(".ant-table-placeholder")


# ---------- 抽屉(Drawer)元素 ----------

def drawer(page: Page):
    """当前可见的新建/编辑抽屉"""
    return page.locator(".ant-drawer-content").last


def drawer_title(page: Page):
    """抽屉标题"""
    return page.locator(".ant-drawer-title").last


def team_name_input(page: Page):
    """班组名称输入框"""
    return page.locator("#teamName")


def building_select(page: Page):
    """楼栋级联选择器 (抽屉内第 1 个 ant-select)"""
    return drawer(page).locator(".ant-select").nth(0)


def member_select(page: Page):
    """班组成员多选器 (抽屉内第 2 个 ant-select)"""
    return drawer(page).locator(".ant-select").nth(1)


def drawer_cancel_btn(page: Page):
    """抽屉取消按钮"""
    return drawer(page).get_by_role("button", name=re.compile(r"取\s*消"))


def drawer_confirm_btn(page: Page):
    """抽屉确定按钮"""
    return drawer(page).get_by_role("button", name=re.compile(r"确\s*定"))


# ---------- 删除确认框 / 提示 ----------

def popconfirm(page: Page):
    """删除确认 Popconfirm"""
    return page.locator(".ant-popconfirm")


def popconfirm_cancel_btn(page: Page):
    """Popconfirm 取消按钮"""
    return page.locator(".ant-popconfirm-buttons .ant-btn-default").last


def popconfirm_confirm_btn(page: Page):
    """Popconfirm 确定按钮"""
    return page.locator(".ant-popconfirm-buttons .ant-btn-primary").last


def message_notice(page: Page):
    """全局提示 toast"""
    return page.locator(".ant-message-notice").last


def member_info_modal(page: Page):
    """关联人数 - 人员信息弹窗"""
    return page.locator(".ant-modal-content").last


def close_modal(page: Page):
    """关闭人员信息弹窗 (Ant Modal 不支持 Escape 关闭, 需点击右上角关闭按钮)"""
    page.locator(".ant-modal-close").last.click()
    expect(member_info_modal(page)).not_to_be_visible(timeout=5000)


# ==================== 辅助函数 ====================

def goto_teams_page(page: Page, page_no: int = 1):
    """导航到班组设置列表页并等待加载就绪"""
    page.goto(f"{TEAMS_BASE_URL}?current={page_no}&pageSize=10", wait_until="networkidle")
    expect(add_team_button(page)).to_be_visible(timeout=15000)


def get_total_count(page: Page) -> int:
    """从分页文案 '第 1-10 条/总共 17 条' 中解析总条数"""
    text = pagination(page).inner_text()
    match = re.search(r"总共\s*(\d+)\s*条", text)
    return int(match.group(1)) if match else team_rows(page).count()


def get_row_by_name(page: Page, name: str, max_pages: int = 3):
    """
    跨页精确查找指定班组名称所在行.
    找到后停留在该页并返回 row locator; 未找到返回 None.
    """
    for page_no in range(1, max_pages + 1):
        goto_teams_page(page, page_no)
        rows = team_rows(page)
        for i in range(rows.count()):
            row = rows.nth(i)
            try:
                if row.locator("td").nth(0).inner_text().strip() == name:
                    return row
            except Exception:
                continue
    return None


def open_create_drawer(page: Page):
    """打开新建班组抽屉并等待就绪"""
    add_team_button(page).click()
    expect(drawer(page)).to_be_visible(timeout=10000)
    expect(drawer_title(page)).to_contain_text("新建班组")


def select_building(page: Page, title: str = "1号楼"):
    """在抽屉中选择楼栋 (级联选择器为单列平铺选项)"""
    building_select(page).click()
    option = page.locator(f".ant-select-dropdown:visible .ant-cascader-menu-item[title='{title}']")
    expect(option.last).to_be_visible(timeout=5000)
    option.last.click()
    expect(building_select(page)).to_contain_text(title)
    # 等待楼栋下拉完全关闭, 避免遮挡后续班组成员选择
    expect(page.locator(".ant-cascader-menus")).not_to_be_visible(timeout=5000)


def select_members(page: Page, count: int = 1):
    """在抽屉中多选班组成员 (选择前 count 个选项)"""
    member_select(page).click()
    dropdown = page.locator(".ant-select-dropdown:visible").last
    options = dropdown.locator(".ant-select-item-option")
    expect(options.first).to_be_visible(timeout=5000)
    available = options.count()
    expected = min(count, available)
    for i in range(expected):
        options.nth(i).click()
    # 用点击抽屉空白区域代替 Escape 关闭下拉:
    # Ant Design 下拉面板挂在 body 根节点上, Escape 关闭后焦点会飘到右上角头像区域,
    # 后续某一步容易误触头像弹出「申请权限/登出」菜单
    drawer(page).click(position={"x": 10, "y": 10})
    expect(page.locator(".ant-select-dropdown:visible")).not_to_be_visible(timeout=5000)
    # 把焦点拉回抽屉内稳定元素, 避免焦点残留导致后续操作偏移
    team_name_input(page).focus()
    # 等待已选标签出现, 确认多选真正生效 (避免点击被下拉遮挡导致未选中)
    expect(
        member_select(page).locator(".ant-select-selection-item")
    ).to_have_count(expected, timeout=5000)


def fill_team_form(page: Page, name: str, building: str = "1号楼", member_count: int = 1):
    """填写班组表单必填项: 班组名称 / 楼栋 / 班组成员"""
    team_name_input(page).fill(name)
    expect(team_name_input(page)).to_have_value(name)
    select_building(page, building)
    select_members(page, member_count)


def create_team(page: Page, name: str, building: str = "1号楼", member_count: int = 1):
    """新建班组并等待提交成功 (抽屉关闭 + 提示文案)"""
    open_create_drawer(page)
    fill_team_form(page, name, building, member_count)
    # 楼栋选择会异步刷新班组成员列表, 可能把已选成员清空; 校验缺失时重选
    tags = member_select(page).locator(".ant-select-selection-item")
    for _ in range(3):
        page.wait_for_timeout(800)
        if tags.count() >= 1:
            break
        select_members(page, member_count)
    drawer_confirm_btn(page).click()
    expect(message_notice(page)).to_contain_text("班组创建成功", timeout=10000)
    expect(drawer(page)).not_to_be_visible(timeout=10000)


def delete_team_if_exists(page: Page, name: str):
    """清理测试数据: 若指定班组存在则删除 (跨页查找)"""
    row = get_row_by_name(page, name)
    if row is None:
        return
    row.get_by_role("button", name="删除").click()
    expect(popconfirm(page)).to_be_visible(timeout=5000)
    popconfirm_confirm_btn(page).click()
    expect(popconfirm(page)).not_to_be_visible(timeout=5000)


def delete_retained_teams(page: Page):
    """删除上次运行保留的班组 (跨页收集所有 RETAINED_TEAM_PREFIX 前缀数据)"""
    names = []
    for page_no in range(1, 4):
        goto_teams_page(page, page_no)
        rows = team_rows(page)
        for i in range(rows.count()):
            try:
                n = rows.nth(i).locator("td").nth(0).inner_text().strip()
            except Exception:
                continue
            if n.startswith(RETAINED_TEAM_PREFIX):
                names.append(n)
    for n in sorted(set(names)):
        delete_team_if_exists(page, n)


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
    ignore_https_errors: 测试环境 (8443) 使用自签名证书, 予以忽略.
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
    """单次登录并进入系统 (session 级, 所有用例复用同一登录态)"""
    page = context.new_page()
    page.set_default_timeout(15000)

    page.goto(LOGIN_URL, wait_until="networkidle")

    username_locator = page.locator("#login")
    password_locator = page.locator("#password")
    login_btn = page.get_by_role("button", name=re.compile(r"登\s*录"))

    expect(username_locator).to_be_editable()
    username_locator.fill(LOGIN_USERNAME)
    password_locator.fill(LOGIN_PASSWORD)
    expect(password_locator).to_have_value(LOGIN_PASSWORD)
    login_btn.click()

    expect(page).to_have_url(re.compile(r"/dashboard|/event"), timeout=20000)

    yield page
    page.close()


@pytest.fixture(scope="session", autouse=True)
def retained_team_lifecycle(logged_in_page: Page):
    """
    保留班组生命周期 (会话级):
    - 运行前: 删除上次运行保留的 RETAINED_TEAM_PREFIX 前缀班组;
    - 运行后: 新建一个 RETAINED_TEAM_PREFIX 前缀班组并保留 (不删除),
      作为 test_kaoqin 新建考勤组时可优先使用的空闲班组.
    """
    delete_retained_teams(logged_in_page)
    yield
    # 运行结束后保留一个新班组 (本次不删除)
    retained_name = f"{RETAINED_TEAM_PREFIX}{int(time.time())}"
    try:
        goto_teams_page(logged_in_page)
        create_team(logged_in_page, retained_name)
    except Exception as e:
        print(f"[retained_team] 保留班组创建失败 (不影响测试结果): {e}")


# ==================== 测试用例 ====================


@allure.feature("值班管理-班组设置")
@allure.label("owner", "自动化测试")
@allure.link("https://stargazer-test.mimiron.cn:8443/login", name="被测系统登录页")
class TestBanZuSheZhi:
    """观星系统 - 值班管理 > 班组设置 E2E 测试"""

    @pytest.fixture(autouse=True)
    def reset_to_teams(self, logged_in_page: Page):
        """每个用例执行前, 统一导航回班组设置列表页, 保证起始状态一致"""
        goto_teams_page(logged_in_page)
        yield

    # ==================== 一、列表页测试 ====================

    @allure.story("班组设置列表页")
    @allure.title("进入班组设置页, 验证搜索区/操作区/表格/分页加载正常")
    @allure.severity(allure.severity_level.BLOCKER)
    def test_teams_page_load(self, logged_in_page: Page):
        with allure.step("验证搜索区元素"):
            expect(search_input(logged_in_page)).to_be_visible()
            expect(search_input(logged_in_page)).to_have_attribute("placeholder", "人员姓名")
            expect(reset_button(logged_in_page)).to_be_visible()
            expect(query_button(logged_in_page)).to_be_visible()

        with allure.step("验证新建班组按钮"):
            expect(add_team_button(logged_in_page)).to_be_visible()

        with allure.step("验证表格列头"):
            # 过滤掉空白字符串 (Ant Design 在有头模式下会追加一个滚动条占位的空 th)
            headers = [
                h.strip()
                for h in logged_in_page.locator(".ant-table-thead th").all_text_contents()
                if h.strip()
            ]
            assert headers == ["班组名称", "楼栋", "关联人数", "操作"], f"表头不正确: {headers}"

        with allure.step("验证分页组件与统计文案"):
            expect(pagination(logged_in_page)).to_be_visible()
            expect(pagination(logged_in_page)).to_contain_text(
                re.compile(r"第\s*1-\d+\s*条/总共\s*\d+\s*条")
            )

    @allure.story("班组设置列表页")
    @allure.title("默认分页展示, 单页最多 10 条数据")
    @allure.severity(allure.severity_level.NORMAL)
    def test_default_page_size(self, logged_in_page: Page):
        total = get_total_count(logged_in_page)

        with allure.step(f"验证第 1 页最多展示 10 条 (当前总数 {total})"):
            expect(team_rows(logged_in_page)).to_have_count(min(10, total))

        with allure.step("验证每行均展示班组名称/楼栋/关联人数/操作"):
            row = team_rows(logged_in_page).first
            cells = [c.strip() for c in row.locator("td").all_text_contents()]
            assert cells[0], "班组名称不应为空"
            assert cells[1], "楼栋不应为空"
            assert re.match(r"^\d+$", cells[2]), f"关联人数应为数字, 实际: {cells[2]}"
            expect(row.get_by_role("button", name="编辑")).to_be_visible()
            expect(row.get_by_role("button", name="删除")).to_be_visible()

    @allure.story("班组设置列表页")
    @allure.title("翻页到第 2 页, 验证分页统计与数据切换")
    @allure.severity(allure.severity_level.NORMAL)
    def test_pagination_to_second_page(self, logged_in_page: Page):
        total = get_total_count(logged_in_page)
        if total <= 10:
            pytest.skip(f"当前数据总量 {total} 条, 无需翻页")

        with allure.step("点击第 2 页"):
            logged_in_page.locator(".ant-pagination-item-2").click()
            expect(logged_in_page).to_have_url(re.compile(r"current=2"), timeout=10000)
            expect(pagination(logged_in_page)).to_contain_text(re.compile(r"第\s*11-\d+\s*条"))

        with allure.step(f"验证第 2 页数据条数 = min(10, 总数 - 10)"):
            expect(team_rows(logged_in_page)).to_have_count(min(10, total - 10))

    @allure.story("班组设置列表页")
    @allure.title("按人员姓名搜索, 验证过滤结果正确")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_search_by_member_name(self, logged_in_page: Page):
        with allure.step("前置: 从首行'关联人数'弹窗获取一个真实成员姓名"):
            first_row = team_rows(logged_in_page).first
            first_row_name = first_row.locator("td").nth(0).inner_text().strip()
            first_row.get_by_role("button").first.click()
            modal = member_info_modal(logged_in_page)
            expect(modal).to_be_visible(timeout=5000)
            member_name = modal.locator("tbody tr").first.locator("td").nth(1).inner_text().strip()
            close_modal(logged_in_page)

        with allure.step(f"按成员姓名 '{member_name}' 查询"):
            search_input(logged_in_page).fill(member_name)
            query_button(logged_in_page).click()
            expect(logged_in_page).to_have_url(re.compile(r"filters\[0\]\[field\]=userName"), timeout=10000)

        with allure.step("验证结果非空且包含该成员所属班组"):
            rows = team_rows(logged_in_page)
            expect(rows.first).to_be_visible(timeout=10000)
            # 一次性读取当前所有行的首列, 避免逐行读取时列表刷新导致定位失效
            names = [n.strip() for n in rows.locator("td:nth-child(1)").all_text_contents()]
            assert first_row_name in names, f"搜索结果应包含 '{first_row_name}', 实际: {names}"

        with allure.step("重置搜索条件"):
            reset_button(logged_in_page).click()
            expect(search_input(logged_in_page)).to_have_value("")

    @allure.story("班组设置列表页")
    @allure.title("按不存在的人员姓名搜索, 验证显示空数据")
    @allure.severity(allure.severity_level.NORMAL)
    def test_search_no_result(self, logged_in_page: Page):
        with allure.step("输入不存在的人员姓名并查询"):
            search_input(logged_in_page).fill("NO_SUCH_USER_ZZZ")
            query_button(logged_in_page).click()
            expect(logged_in_page).to_have_url(re.compile(r"NO_SUCH_USER_ZZZ"), timeout=10000)

        with allure.step("验证表格显示'暂无数据'"):
            expect(empty_placeholder(logged_in_page)).to_contain_text("暂无数据", timeout=10000)
            expect(team_rows(logged_in_page)).to_have_count(0)

        with allure.step("重置搜索"):
            reset_button(logged_in_page).click()
            expect(search_input(logged_in_page)).to_have_value("")

    @allure.story("班组设置列表页")
    @allure.title("搜索框输入特殊字符, 验证系统安全处理不报错")
    @allure.severity(allure.severity_level.NORMAL)
    def test_search_special_characters(self, logged_in_page: Page):
        payload = "<script>alert('xss')</script>"

        with allure.step(f"输入特殊字符: {payload}"):
            search_input(logged_in_page).fill(payload)
            query_button(logged_in_page).click()
            logged_in_page.wait_for_load_state("networkidle")

        with allure.step("验证页面未崩溃, 搜索框与表格仍正常显示"):
            expect(search_input(logged_in_page)).to_be_visible()
            expect(logged_in_page.locator(".ant-table").first).to_be_visible()
            expect(add_team_button(logged_in_page)).to_be_visible()

        with allure.step("重置搜索"):
            reset_button(logged_in_page).click()
            expect(search_input(logged_in_page)).to_have_value("")

    @allure.story("班组设置列表页")
    @allure.title("点击关联人数, 验证人员信息弹窗与成员数量一致")
    @allure.severity(allure.severity_level.NORMAL)
    def test_member_count_modal(self, logged_in_page: Page):
        row = team_rows(logged_in_page).first
        count_text = row.locator("td").nth(2).inner_text().strip()
        expected = int(count_text)

        with allure.step(f"点击关联人数 ({expected} 人)"):
            row.get_by_role("button").first.click()
            modal = member_info_modal(logged_in_page)
            expect(modal).to_be_visible(timeout=5000)

        with allure.step("验证弹窗标题与表头"):
            expect(logged_in_page.locator(".ant-modal-title").last).to_contain_text("人员信息")
            headers = [h.strip() for h in modal.locator("thead th").all_text_contents()]
            assert headers == ["人员工号", "人员姓名"], f"人员信息表头不正确: {headers}"

        with allure.step(f"验证列表行数等于关联人数 {expected}"):
            expect(modal.locator("tbody tr")).to_have_count(expected)

        with allure.step("关闭弹窗"):
            close_modal(logged_in_page)

    # ==================== 二、新建班组测试 ====================

    @allure.story("新建班组")
    @allure.title("点击新建班组, 验证抽屉打开且字段完整")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_open_create_drawer(self, logged_in_page: Page):
        with allure.step("点击新建班组按钮"):
            open_create_drawer(logged_in_page)

        with allure.step("验证表单字段可见"):
            expect(team_name_input(logged_in_page)).to_be_visible()
            expect(team_name_input(logged_in_page)).to_have_attribute("placeholder", "请输入班组名称")
            expect(building_select(logged_in_page)).to_be_visible()
            expect(building_select(logged_in_page)).to_contain_text("请选择楼栋")
            expect(member_select(logged_in_page)).to_be_visible()
            expect(member_select(logged_in_page)).to_contain_text("请选择班组成员")

        with allure.step("验证底部按钮"):
            expect(drawer_cancel_btn(logged_in_page)).to_be_visible()
            expect(drawer_confirm_btn(logged_in_page)).to_be_visible()

        with allure.step("点击取消关闭抽屉"):
            drawer_cancel_btn(logged_in_page).click()
            expect(drawer(logged_in_page)).not_to_be_visible(timeout=5000)

    @allure.story("新建班组")
    @allure.title("空表单提交, 验证三项必填校验提示")
    @allure.severity(allure.severity_level.NORMAL)
    def test_create_empty_validation(self, logged_in_page: Page):
        with allure.step("打开新建抽屉, 不填写任何内容直接提交"):
            open_create_drawer(logged_in_page)
            drawer_confirm_btn(logged_in_page).click()

        with allure.step("验证抽屉未关闭且出现三项必填校验"):
            expect(drawer(logged_in_page)).to_be_visible()
            errors = [
                e.inner_text().strip()
                for e in logged_in_page.locator(".ant-form-item-explain-error").all()
            ]
            assert "请输入班组名称" in errors, f"缺少班组名称校验: {errors}"
            assert "请选择楼栋" in errors, f"缺少楼栋校验: {errors}"
            assert "请选择班组成员" in errors, f"缺少班组成员校验: {errors}"

        with allure.step("关闭抽屉"):
            drawer_cancel_btn(logged_in_page).click()
            expect(drawer(logged_in_page)).not_to_be_visible(timeout=5000)

    @allure.story("新建班组")
    @allure.title("仅填写班组名称提交, 验证楼栋与成员校验")
    @allure.severity(allure.severity_level.NORMAL)
    def test_create_partial_validation(self, logged_in_page: Page):
        with allure.step("只填写班组名称"):
            open_create_drawer(logged_in_page)
            team_name_input(logged_in_page).fill(f"{TEST_TEAM_PREFIX}部分_{int(time.time())}")

        with allure.step("提交并验证仅剩楼栋/成员两项校验"):
            drawer_confirm_btn(logged_in_page).click()
            expect(drawer(logged_in_page)).to_be_visible()
            errors = [
                e.inner_text().strip()
                for e in logged_in_page.locator(".ant-form-item-explain-error").all()
            ]
            assert "请选择楼栋" in errors, f"缺少楼栋校验: {errors}"
            assert "请选择班组成员" in errors, f"缺少班组成员校验: {errors}"
            assert "请输入班组名称" not in errors, "已填写名称, 不应再提示名称必填"

        with allure.step("关闭抽屉"):
            drawer_cancel_btn(logged_in_page).click()
            expect(drawer(logged_in_page)).not_to_be_visible(timeout=5000)

    @allure.story("新建班组")
    @allure.title("填写完整信息新建班组, 验证创建成功并出现在列表")
    @allure.severity(allure.severity_level.BLOCKER)
    def test_create_team_success(self, logged_in_page: Page):
        team_name = f"{TEST_TEAM_PREFIX}新建_{int(time.time())}"

        try:
            with allure.step(f"新建班组: {team_name}"):
                create_team(logged_in_page, team_name)

            with allure.step("刷新列表并验证新增班组存在"):
                row = get_row_by_name(logged_in_page, team_name)
                assert row is not None, f"新建班组 '{team_name}' 未出现在列表中"
                assert row.locator("td").nth(1).inner_text().strip() == "1号楼"
                assert int(row.locator("td").nth(2).inner_text().strip()) >= 1

        finally:
            with allure.step("清理测试数据"):
                delete_team_if_exists(logged_in_page, team_name)

    @allure.story("新建班组")
    @allure.title("填写信息后取消, 验证抽屉关闭且未创建数据")
    @allure.severity(allure.severity_level.NORMAL)
    def test_create_team_cancel(self, logged_in_page: Page):
        team_name = f"{TEST_TEAM_PREFIX}取消_{int(time.time())}"

        with allure.step(f"打开抽屉并填写信息: {team_name}"):
            open_create_drawer(logged_in_page)
            fill_team_form(logged_in_page, team_name)

        with allure.step("点击取消"):
            drawer_cancel_btn(logged_in_page).click()
            expect(drawer(logged_in_page)).not_to_be_visible(timeout=5000)

        with allure.step("刷新列表, 验证该班组未创建"):
            row = get_row_by_name(logged_in_page, team_name)
            assert row is None, f"取消新建后, 班组 '{team_name}' 不应存在"

    @allure.story("新建班组")
    @allure.title("使用已存在的班组名称新建, 验证重名校验")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_create_duplicate_name(self, logged_in_page: Page):
        with allure.step("获取列表中已存在的班组名称"):
            existing_name = team_rows(logged_in_page).first.locator("td").nth(0).inner_text().strip()

        with allure.step(f"使用重复名称 '{existing_name}' 新建班组"):
            open_create_drawer(logged_in_page)
            fill_team_form(logged_in_page, existing_name)
            drawer_confirm_btn(logged_in_page).click()

        with allure.step("验证提示'数据或名称不能重复'且抽屉保持打开"):
            expect(message_notice(logged_in_page)).to_contain_text(
                "数据或名称不能重复", timeout=10000
            )
            expect(drawer(logged_in_page)).to_be_visible()

        with allure.step("关闭抽屉"):
            drawer_cancel_btn(logged_in_page).click()
            expect(drawer(logged_in_page)).not_to_be_visible(timeout=5000)

    @allure.story("新建班组")
    @allure.title("选择多个班组成员, 验证多选生效")
    @allure.severity(allure.severity_level.NORMAL)
    def test_member_multi_select(self, logged_in_page: Page):
        with allure.step("打开抽屉并选择 2 个班组成员"):
            open_create_drawer(logged_in_page)
            select_members(logged_in_page, count=2)

        with allure.step("验证成员选择器展示 2 个已选标签"):
            selected_tags = member_select(logged_in_page).locator(".ant-select-selection-item")
            expect(selected_tags).to_have_count(2)

        with allure.step("关闭抽屉"):
            drawer_cancel_btn(logged_in_page).click()
            expect(drawer(logged_in_page)).not_to_be_visible(timeout=5000)

    @allure.story("新建班组")
    @allure.title("展开楼栋级联选择器, 验证楼栋选项完整")
    @allure.severity(allure.severity_level.NORMAL)
    def test_building_options(self, logged_in_page: Page):
        with allure.step("打开新建抽屉并展开楼栋选择器"):
            open_create_drawer(logged_in_page)
            building_select(logged_in_page).click()
            dropdown = logged_in_page.locator(".ant-select-dropdown:visible").last
            items = dropdown.locator(".ant-cascader-menu-item")
            expect(items.first).to_be_visible(timeout=5000)

        with allure.step("验证楼栋选项包含园区楼与各楼栋"):
            # 下拉选项可能延迟渲染/重渲染, 轮询等待选项齐全后再收集
            titles = []
            for _ in range(10):
                items = logged_in_page.locator(
                    ".ant-select-dropdown:visible .ant-cascader-menu-item"
                )
                titles = [t.strip() for t in items.all_text_contents() if t.strip()]
                if len(titles) >= 5:
                    break
                logged_in_page.wait_for_timeout(500)
            for expected in ["园区楼", "1号楼", "2号楼", "6号测试楼", "5号-测试楼"]:
                assert any(expected in t for t in titles), \
                    f"楼栋选项缺少 '{expected}', 实际: {titles}"

        with allure.step("关闭下拉与抽屉"):
            logged_in_page.keyboard.press("Escape")
            drawer_cancel_btn(logged_in_page).click()
            expect(drawer(logged_in_page)).not_to_be_visible(timeout=5000)

    # ==================== 三、编辑班组测试 ====================

    @allure.story("编辑班组")
    @allure.title("编辑班组, 验证数据回填且修改名称成功")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_edit_team(self, logged_in_page: Page):
        original_name = f"{TEST_TEAM_PREFIX}编辑原_{int(time.time())}"
        edited_name = f"{TEST_TEAM_PREFIX}编辑后_{int(time.time())}"

        try:
            with allure.step("前置: 新建一个班组"):
                create_team(logged_in_page, original_name)

            with allure.step("点击编辑, 验证抽屉标题与数据回填"):
                row = get_row_by_name(logged_in_page, original_name)
                assert row is not None, f"前置班组 '{original_name}' 未创建成功"
                row.get_by_role("button", name="编辑").click()
                expect(drawer(logged_in_page)).to_be_visible(timeout=10000)
                expect(drawer_title(logged_in_page)).to_contain_text("编辑班组")
                expect(team_name_input(logged_in_page)).to_have_value(original_name)
                expect(building_select(logged_in_page)).to_contain_text("1号楼")
                expect(
                    member_select(logged_in_page).locator(".ant-select-selection-item")
                ).not_to_have_count(0)

            with allure.step(f"修改名称为: {edited_name}"):
                team_name_input(logged_in_page).fill(edited_name)
                drawer_confirm_btn(logged_in_page).click()
                expect(drawer(logged_in_page)).not_to_be_visible(timeout=10000)

            with allure.step("验证列表显示编辑后的名称"):
                assert get_row_by_name(logged_in_page, edited_name) is not None, \
                    f"编辑后班组 '{edited_name}' 未出现在列表中"

        finally:
            with allure.step("清理测试数据"):
                delete_team_if_exists(logged_in_page, original_name)
                delete_team_if_exists(logged_in_page, edited_name)

    @allure.story("编辑班组")
    @allure.title("编辑后点击取消, 验证数据未被修改")
    @allure.severity(allure.severity_level.NORMAL)
    def test_edit_team_cancel(self, logged_in_page: Page):
        original_name = f"{TEST_TEAM_PREFIX}编辑取消_{int(time.time())}"
        temp_name = f"{TEST_TEAM_PREFIX}临时名_{int(time.time())}"

        try:
            with allure.step("前置: 新建一个班组"):
                create_team(logged_in_page, original_name)

            with allure.step("打开编辑并修改名称后取消"):
                row = get_row_by_name(logged_in_page, original_name)
                assert row is not None, f"前置班组 '{original_name}' 未创建成功"
                row.get_by_role("button", name="编辑").click()
                expect(drawer(logged_in_page)).to_be_visible(timeout=10000)
                team_name_input(logged_in_page).fill(temp_name)
                drawer_cancel_btn(logged_in_page).click()
                expect(drawer(logged_in_page)).not_to_be_visible(timeout=5000)

            with allure.step("验证原名称仍存在, 临时名称不存在"):
                assert get_row_by_name(logged_in_page, original_name) is not None, \
                    f"取消编辑后原班组 '{original_name}' 应仍存在"
                assert get_row_by_name(logged_in_page, temp_name) is None, \
                    f"取消编辑后不应出现 '{temp_name}'"

        finally:
            with allure.step("清理测试数据"):
                delete_team_if_exists(logged_in_page, original_name)
                delete_team_if_exists(logged_in_page, temp_name)

    # ==================== 四、删除班组测试 ====================

    @allure.story("删除班组")
    @allure.title("删除时点击取消, 验证班组未被删除")
    @allure.severity(allure.severity_level.NORMAL)
    def test_delete_team_cancel(self, logged_in_page: Page):
        team_name = f"{TEST_TEAM_PREFIX}删取消_{int(time.time())}"

        try:
            with allure.step("前置: 新建一个班组"):
                create_team(logged_in_page, team_name)

            with allure.step("点击删除, 验证确认框文案"):
                row = get_row_by_name(logged_in_page, team_name)
                assert row is not None, f"前置班组 '{team_name}' 未创建成功"
                row.get_by_role("button", name="删除").click()
                expect(popconfirm(logged_in_page)).to_be_visible(timeout=5000)
                expect(popconfirm(logged_in_page)).to_contain_text("确认删除该班组？")

            with allure.step("点击取消"):
                popconfirm_cancel_btn(logged_in_page).click()
                expect(popconfirm(logged_in_page)).not_to_be_visible(timeout=5000)

            with allure.step("验证班组仍存在"):
                assert get_row_by_name(logged_in_page, team_name) is not None, \
                    f"取消删除后班组 '{team_name}' 应仍存在"

        finally:
            with allure.step("清理测试数据"):
                delete_team_if_exists(logged_in_page, team_name)

    @allure.story("删除班组")
    @allure.title("确认删除, 验证班组从列表移除")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_delete_team_confirm(self, logged_in_page: Page):
        team_name = f"{TEST_TEAM_PREFIX}删确认_{int(time.time())}"

        with allure.step("前置: 新建一个班组"):
            create_team(logged_in_page, team_name)

        with allure.step("点击删除并确认"):
            row = get_row_by_name(logged_in_page, team_name)
            assert row is not None, f"前置班组 '{team_name}' 未创建成功"
            row.get_by_role("button", name="删除").click()
            expect(popconfirm(logged_in_page)).to_be_visible(timeout=5000)
            popconfirm_confirm_btn(logged_in_page).click()
            expect(popconfirm(logged_in_page)).not_to_be_visible(timeout=5000)

        with allure.step("验证班组已从列表移除"):
            assert get_row_by_name(logged_in_page, team_name) is None, \
                f"确认删除后班组 '{team_name}' 应不存在"
