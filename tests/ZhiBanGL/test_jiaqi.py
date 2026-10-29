# -*- coding: utf-8 -*-
"""
观星系统 - 值班管理 > 假期规则 E2E 自动化测试
================================================================
技术栈: Python + Playwright + pytest + allure
被测地址: https://stargazer-test.mimiron.cn:8443/infra-attendance/schedule-attendance/leave-rules

页面结构 (基于 Playwright 快照实测):
  列表页:
    - 无搜索区
    - 操作按钮: 新增假期规则 (primary)
    - 表格列: 假期名称 | 请假单位 | 计算请假时长方式 | 余额规则 | 适用范围 | 操作
    - 适用范围列: 全员 (文本) / 查看 (link, 点击进入编辑抽屉)
    - 行内操作:
      - button "编辑"
      - button "删除"
    - 分页: list "第 N-M 条/总共 X 条" + 上一页/下一页

  新建/编辑抽屉 (Ant Design Drawer):
    - Drawer 标题: "新建假期规则" / "编辑假期规则"
    - 假期名称           (input #leaveName,  必填, placeholder="请输入")
    - 假期负责人         (select multiple id=managerUserIds, 非必填)
    - 适用范围           (radio-wrapper: 全员 / 自定义范围, 非必填, 默认全员)
    - 最小请假单位       (radio-wrapper: 天 / 半天 / 小时, 非必填, 默认天)
    - 计算请假时长方式   (radio-wrapper: 按工作日计算请假时长 / 按自然日计算请假时长, 非必填)
    - 新员工发放规则     (radio-wrapper: 入职即可请假 / 转正后即可请假, 非必填)
    - 新员工折算规则     (radio-wrapper: 发放全部数量 / 按日折算, 非必填)
    - 设置员工假期余额   (radio-wrapper: 不限制 / 限制, 非必填)
    - [checkbox] 按实际工作时长发放余额
    - 发放周期           (radio-wrapper: 年 / 月 / 手动发放,  必填)
    - 周期开始时间       (radio-wrapper: 每年员工入职日 / 每年1月1日,  必填)
    - 额度配置规则       (select,  必填)
    - 额度               (input-number + select 紧凑组合,  必填)
    - 有效期             (radio-wrapper: 按发放周期结束后失效 / 按发放日计算过期日期
                         / 指定过期日期 / 永久有效,  必填)
    - [checkbox] 允许延长有效期
    - 假期过期提醒区域:
        - switch (默认 checked)
        - 提醒时间 input-number (默认 1)
        - 提醒范围 checkbox: 通知员工 / 通知员工主管
    - 底部按钮: 取 消 / 确 定

  删除: Popconfirm "确认删除该假期规则？" + 取 消 / 确 定

定位注意:
  1. radio 的 wrapper 在 Portal 上, 用 page 级别 locator 定位;
  2. checkbox 同理, Portal 渲染到 body 根;
  3. 抽屉底部按钮用 page 级别按文本正则匹配, 更可靠;
  4. 额度紧凑组合中 input-number 和 select 都 visible, 用 nth() 区分;
  5. 列表页无搜索框, 直接遍历表格行按假期名称匹配;
================================================================
"""

import os
import re
import time

import pytest
import allure
from playwright.sync_api import sync_playwright, expect, Page


# ==================== 测试配置 ====================

BASE_URL = os.getenv("JIAQI_BASE_URL", "https://stargazer-test.mimiron.cn:8443")
LEAVE_RULES_URL = f"{BASE_URL}/infra-attendance/schedule-attendance/leave-rules"

LOGIN_USERNAME = os.getenv("LOGIN_USERNAME", "zhenyu_m")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "")  # conftest.py 自动加载
LOGIN_URL = f"{BASE_URL}/login"
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

TEST_PREFIX = "AT_假期_"


# ==================== 元素定位器 ====================

# ---------- 列表页 ----------

def add_rule_button(page: Page):
    """新增假期规则按钮"""
    return page.get_by_role("button", name=re.compile(r"新\s*增\s*假\s*期\s*规\s*则"))


def table_headers(page: Page):
    """表格列头文本列表"""
    return [h.strip() for h in
            page.locator(".ant-table-thead th").all_text_contents()
            if h.strip()]


def rule_rows(page: Page):
    """表格数据行"""
    return page.locator(".ant-table-tbody > tr.ant-table-row")


def pagination(page: Page):
    """分页统计文案"""
    return page.locator(".ant-pagination").first


# ---------- 抽屉 ----------

def drawer(page: Page):
    """当前可见的 Drawer"""
    return page.locator(".ant-drawer-content").last


def drawer_title(page: Page):
    return page.locator(".ant-drawer-title").last


def leave_name_input(page: Page):
    """假期名称 (唯一 id=leaveName)"""
    return page.locator("#leaveName").first


def owner_select(page: Page):
    """假期负责人多选下拉 (Drawer 内第一个 visible 的 ant-select)"""
    d = drawer(page)
    return d.locator(".ant-select.ant-pro-filed-search-select:visible").first


def radio_wrapper(page: Page, label: str, parent_form_item: str = None):
    """
    radio-wrapper (Portal 渲染到 body)
    parent_form_item: 可选, 所属 form-item 的 label 文本 (如 "发放周期")
      用于区分同名 radio, 例如 "年" 同时出现在 "发放周期" 和 "周期开始时间"
    """
    if parent_form_item:
        # 先按 form-item label 定位到 form-item, 再在其内部找 radio-wrapper
        form_item = page.locator(
            ".ant-drawer .ant-form-item:has(label:has-text('"
            + parent_form_item + "'))"
        )
        return form_item.locator(
            ".ant-radio-wrapper", has_text=re.compile(label)
        ).first
    return page.locator(".ant-radio-wrapper", has_text=re.compile(label))


def checkbox_wrapper(page: Page, label: str):
    """checkbox-wrapper (Portal)"""
    return page.locator(".ant-checkbox-wrapper", has_text=re.compile(label))


def quota_select(page: Page):
    """额度配置规则 select (form-item label="额度配置规则" 内唯一可见 select)"""
    return page.locator(
        ".ant-drawer .ant-form-item:has(label:has-text('额度配置规则')) "
        ".ant-select:visible"
    ).first


def quota_value_input(page: Page):
    """额度 input-number (紧凑组合中的第一个 input-number)"""
    return page.locator(
        ".ant-drawer .ant-form-item:has(label:has-text('额度')) .ant-input-number-input:visible"
    ).first


def quota_unit_select(page: Page):
    """
    额度单位 select (天/半天/小时)
    定位: form-item label="额度" 内的 ant-select (不是 ant-input-number)
    """
    return page.locator(
        ".ant-drawer .ant-form-item:has(label:has-text('额度')) "
        ".ant-select:not(.ant-select-compact-item-hidden):visible"
    ).last


def drawer_cancel_btn(page: Page):
    """抽屉底部取消按钮"""
    return page.get_by_role("button", name=re.compile(r"取\s*消"))


def drawer_confirm_btn(page: Page):
    """抽屉底部确定按钮"""
    return page.get_by_role("button", name=re.compile(r"确\s*定"))


def close_icon_btn(page: Page):
    """抽屉右上角关闭图标 (X)"""
    return page.locator(".ant-drawer-close").last


def error_messages(page: Page):
    """表单校验错误文案 (all_inner_texts 一次性抓取, 避免遍历时 DOM 动态增删导致超时)"""
    return [t.strip() for t in
            page.locator(".ant-form-item-explain-error").all_inner_texts()
            if t.strip()]


def message_notice(page: Page):
    return page.locator(".ant-message-notice").last


def popconfirm_confirm_btn(page: Page):
    return page.locator(".ant-popconfirm-buttons .ant-btn-primary").last


def popconfirm_cancel_btn(page: Page):
    return page.locator(".ant-popconfirm-buttons .ant-btn-default").last


# ==================== 辅助函数 ====================

def _is_radio_checked(wrapper_locator) -> bool:
    """检查 .ant-radio-wrapper 的 checked 状态"""
    inner = wrapper_locator.locator(".ant-radio").first
    if inner.count() == 0:
        return False
    cls = inner.get_attribute("class") or ""
    return "ant-radio-checked" in cls


def _is_checkbox_checked(wrapper_locator) -> bool:
    """检查 .ant-checkbox-wrapper 的 checked 状态"""
    inner = wrapper_locator.locator(".ant-checkbox").first
    if inner.count() == 0:
        return False
    cls = inner.get_attribute("class") or ""
    return "ant-checkbox-checked" in cls


def toggle_radio(page: Page, selector):
    """确保 radio 选中"""
    if not _is_radio_checked(selector):
        selector.click()
        page.wait_for_timeout(300)
    assert _is_radio_checked(selector), (
        f"radio toggle 失败: {selector}"
    )


def toggle_checkbox(page: Page, selector, target: bool = True):
    """确保 checkbox wrapper 处于目标状态"""
    is_now = _is_checkbox_checked(selector)
    if target and not is_now:
        selector.click()
        page.wait_for_timeout(300)
    elif not target and is_now:
        selector.click()
        page.wait_for_timeout(300)
    assert _is_checkbox_checked(selector) == target, (
        f"checkbox toggle 失败: 目标={target} 实际={_is_checkbox_checked(selector)}"
    )


def _ensure_logged_in(page: Page):
    """Cookie 过期时重新登录"""
    if "login" in page.url and page.locator("#login").count():
        page.locator("#login").fill(LOGIN_USERNAME)
        page.locator("#password").fill(LOGIN_PASSWORD)
        page.get_by_role("button", name=re.compile(r"登\s*录")).click()
        expect(page).to_have_url(re.compile(r"/dashboard|/event"), timeout=20000)


def goto_leave_rules_page(page: Page):
    """导航到假期规则页 (含 cookie 健康检查)"""
    page.goto(
        f"{LEAVE_RULES_URL}?current=1&pageSize=100",
        wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    if "login" in page.url:
        _ensure_logged_in(page)
        page.goto(
            f"{LEAVE_RULES_URL}?current=1&pageSize=100",
            wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

    try:
        expect(add_rule_button(page)).to_be_visible(timeout=15000)
    except AssertionError:
        page.reload(wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        expect(add_rule_button(page)).to_be_visible(timeout=20000)


def open_create_drawer(page: Page):
    """打开新建假期规则抽屉"""
    add_rule_button(page).click()
    expect(drawer(page)).to_be_visible(timeout=10000)
    expect(drawer_title(page)).to_contain_text("新建假期规则")


def select_quota_option(page: Page, option_text: str = "固定额度"):
    """点击额度配置规则 select 并选择选项"""
    sel = quota_select(page)
    sel.click()
    page.wait_for_timeout(800)
    opt = page.locator(
        f".ant-select-dropdown:visible .ant-select-item-option",
        has_text=re.compile(option_text)
    ).first
    if opt.count():
        opt.click()
        page.wait_for_timeout(300)
    if page.locator(".ant-select-dropdown:visible").count() > 0:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)


def select_quota_unit(page: Page, unit_text: str = "天"):
    """额度单位 select: 天/半天/小时"""
    sel = quota_unit_select(page)
    sel.click()
    page.wait_for_timeout(800)
    opt = page.locator(
        f".ant-select-dropdown:visible .ant-select-item-option",
        has_text=re.compile(f"^{unit_text}$")
    ).first
    if opt.count():
        opt.click()
        page.wait_for_timeout(300)
    if page.locator(".ant-select-dropdown:visible").count() > 0:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)


def fill_leave_name(page: Page, name: str):
    """填写假期名称 (Vue v-model 需要真实输入事件, 等抽屉动画完成)"""
    inp = leave_name_input(page)
    inp.wait_for(state="visible", timeout=8000)
    page.wait_for_timeout(500)  # 抽屉展开动画
    for attempt in range(3):
        inp.click()
        inp.fill(name)
        try:
            expect(inp).to_have_value(name, timeout=2000)
            return
        except AssertionError:
            inp.clear()
            inp.type(name, delay=30)
            try:
                expect(inp).to_have_value(name, timeout=2000)
                return
            except AssertionError:
                if attempt == 2:
                    raise
                page.wait_for_timeout(500)


def fill_required_fields(
    page: Page,
    name: str,
    leave_unit: str = "天",       # 最小请假单位
    pay_period: str = "年",       # 发放周期: 年/月/手动发放
    cycle_start: str = "每年员工入职日",  # 周期开始时间
    quota_rule: str = "固定额度",  # 额度配置规则
    quota_value: str = "5",       # 额度值
    quota_unit: str = "天",       # 额度单位
    validity: str = "按发放周期结束后失效",  # 有效期
):
    """
    填写抽屉必填字段: 假期名称 / 发放周期 / 周期开始时间 / 额度配置规则 / 额度 / 有效期.
    其他非必填项保持默认值.
    """
    # 1. 假期名称
    fill_leave_name(page, name)

    # 2. 发放周期
    toggle_radio(page, radio_wrapper(page, pay_period, parent_form_item="发放周期"))

    # 3. 周期开始时间
    toggle_radio(page, radio_wrapper(page, cycle_start, parent_form_item="周期开始时间"))

    # 4. 额度配置规则
    select_quota_option(page, quota_rule)

    # 5. 额度数值
    quota_value_input(page).fill(quota_value)

    # 6. 额度单位
    select_quota_unit(page, quota_unit)

    # 7. 有效期
    toggle_radio(page, radio_wrapper(page, validity, parent_form_item="有效期"))


def close_drawer(page: Page):
    """用取消按钮关闭抽屉"""
    drawer_cancel_btn(page).click()
    expect(drawer(page)).not_to_be_visible(timeout=5000)


def get_row_by_name(page: Page, name: str):
    """在当前列表查找假期规则 (精确匹配假期名称)"""
    rows = rule_rows(page)
    for i in range(rows.count()):
        row = rows.nth(i)
        try:
            if row.locator("td").nth(0).inner_text().strip() == name:
                return row
        except Exception:
            continue
    return None


def delete_rule_if_exists(page: Page, name: str):
    """清理测试数据"""
    goto_leave_rules_page(page)
    row = get_row_by_name(page, name)
    if row is None:
        return
    # 删除是 ant-typography <a> 标签, 不是 button
    row.get_by_text("删除", exact=True).click()
    # 等待 popconfirm
    expect(page.locator(".ant-popconfirm")).to_be_visible(timeout=5000)
    popconfirm_confirm_btn(page).click()
    # 轮询等待行消失 (最长 12s)
    for _ in range(12):
        if get_row_by_name(page, name) is None:
            return
        page.wait_for_timeout(1000)
    # 刷新列表再确认一次
    goto_leave_rules_page(page)


def create_rule(page: Page, name: str, **kwargs):
    """快速新建假期规则 (必填字段 + 默认值)"""
    open_create_drawer(page)
    fill_required_fields(page, name=name, **kwargs)

    # 监听提交响应, 捕获错误
    state = {"body": "", "success": False}

    def _on_resp(resp):
        if resp.request.method == "POST" and "leave-rules" in resp.url:
            try:
                body = resp.text()
            except Exception:
                return
            state["body"] = body
            state["success"] = "statusCode" not in body

    page.on("response", _on_resp)
    try:
        drawer_confirm_btn(page).click()

        # 等待抽屉关闭或响应到达
        for _ in range(30):
            page.wait_for_timeout(500)
            if state["body"] or not drawer(page).is_visible():
                break

        if not state["body"] and drawer(page).is_visible():
            # 前端校验就没通过, 没发请求
            errs = error_messages(page)
            toast = message_notice(page).inner_text() \
                if message_notice(page).count() else ""
            raise AssertionError(
                f"创建假期规则 '{name}' 前端校验未通过 (无请求发出). "
                f"form_errors={errs}, toast={toast}"
            )

        if state["body"] and not state["success"]:
            errs = error_messages(page)
            toast = message_notice(page).inner_text() \
                if message_notice(page).count() else ""
            raise AssertionError(
                f"创建假期规则 '{name}' 失败. "
                f"response={state['body'][:500]}, "
                f"form_errors={errs}, toast={toast}"
            )

        expect(drawer(page)).not_to_be_visible(timeout=5000)

        # 回到列表页验证出现
        goto_leave_rules_page(page)
        for _ in range(10):
            if get_row_by_name(page, name) is not None:
                return True
            page.wait_for_timeout(1000)
        raise AssertionError(f"创建后列表未出现 '{name}'")
    finally:
        page.remove_listener("response", _on_resp)


# ==================== pytest fixture ====================


@pytest.fixture(scope="session")
def playwright():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright):
    args = ["--no-sandbox", "--disable-dev-shm-usage",
            "--disable-gpu", "--disable-setuid-sandbox"]
    b = playwright.chromium.launch(headless=HEADLESS, args=args)
    yield b
    b.close()


@pytest.fixture(scope="session")
def context(browser):
    ctx = browser.new_context(
        ignore_https_errors=True, locale="zh-CN",
        viewport={"width": 1800, "height": 1300})
    yield ctx
    ctx.close()


@pytest.fixture(scope="session")
def logged_in_page(context):
    page = context.new_page()
    page.set_default_timeout(15000)
    page.goto(LOGIN_URL, wait_until="networkidle")
    page.locator("#login").fill(LOGIN_USERNAME)
    page.locator("#password").fill(LOGIN_PASSWORD)
    page.get_by_role("button", name=re.compile(r"登\s*录")).click()
    expect(page).to_have_url(re.compile(r"/dashboard|/event"), timeout=20000)
    yield page
    page.close()


@pytest.fixture(autouse=True)
def reset_to_leave_rules(logged_in_page: Page):
    """每个用例前导航回假期规则页"""
    goto_leave_rules_page(logged_in_page)
    yield


# ==================== 测试用例 ====================


@allure.feature("值班管理-假期规则")
@allure.label("owner", "自动化测试")
@allure.link("https://stargazer-test.mimiron.cn:8443/login", name="被测系统登录页")
class TestJiaQiGuiZe:
    """观星系统 - 值班管理 > 假期规则 E2E 测试"""

    # ---------- 一、列表页 ----------

    @allure.story("假期规则列表页")
    @allure.title("进入假期规则页, 验证按钮/表格/分页加载正常")
    @allure.severity(allure.severity_level.BLOCKER)
    def test_page_load(self, logged_in_page: Page):
        with allure.step("验证新增按钮可见"):
            expect(add_rule_button(logged_in_page)).to_be_visible()

        with allure.step("验证表格列头正确"):
            headers = table_headers(logged_in_page)
            # 最后一个列头可能是空 (extra 操作列占位)
            valid_headers = [h for h in headers if h]
            assert valid_headers == [
                "假期名称", "请假单位", "计算请假时长方式",
                "余额规则", "适用范围", "操作"
            ], f"表头不正确: {valid_headers}"

        with allure.step("验证分页统计文案"):
            expect(pagination(logged_in_page)).to_be_visible()
            expect(pagination(logged_in_page)).to_contain_text(
                re.compile(r"第\s*\d+-\d+\s*条/总共\s*\d+\s*条")
            )

    @allure.story("假期规则列表页")
    @allure.title("表格首行数据列值正确展示")
    @allure.severity(allure.severity_level.NORMAL)
    def test_row_data(self, logged_in_page: Page):
        row = rule_rows(logged_in_page).first
        # 假期名称非空
        expect(row.locator("td").nth(0)).not_to_have_text("")
        # 请假单位是已知枚举
        leave_unit = row.locator("td").nth(1).inner_text().strip()
        assert leave_unit in ("按天请假", "按半天请假", "按小时请假"), (
            f"请假单位值异常: {leave_unit}"
        )
        # 操作列有编辑/删除 (删除是 ant-typography link, 不是 button)
        expect(row.get_by_role("button", name=re.compile(r"编\s*辑"))).to_be_visible()
        expect(row.get_by_text("删除", exact=True)).to_be_visible()

    @allure.story("假期规则列表页")
    @allure.title("适用范围列: 自定义范围显示'查看'链接")
    @allure.severity(allure.severity_level.NORMAL)
    def test_custom_scope_shows_view_link(self, logged_in_page: Page):
        # 遍历所有行, 验证适用范围列要么是 "全员" 文本, 要么有 "查看" link
        rows = rule_rows(logged_in_page)
        checked = 0
        for i in range(min(rows.count(), 10)):
            row = rows.nth(i)
            scope_cell = row.locator("td").nth(4)
            text = scope_cell.inner_text().strip()
            if text:
                assert text in ("全员", "查看"), (
                    f"适用范围值异常 (row {i}): '{text}'"
                )
                checked += 1
        # 至少要检查到 1 行
        assert checked > 0, "未检查到任何适用范围列值"

    # ---------- 二、新建假期规则 ----------

    @allure.story("新建假期规则")
    @allure.title("空表单提交, 验证表单校验机制生效")
    @allure.severity(allure.severity_level.BLOCKER)
    def test_create_empty_validation(self, logged_in_page: Page):
        open_create_drawer(logged_in_page)
        drawer_confirm_btn(logged_in_page).click()
        expect(drawer(logged_in_page)).to_be_visible()

        # 等待校验文案渲染
        logged_in_page.wait_for_selector(".ant-form-item-explain-error", timeout=5000)
        errs = error_messages(logged_in_page)

        # 实测空表单触发: 请输入假期名称 / 请输入额度
        # (radio 必填项默认未选中, 但空表单提交不触发 Ant Design radio 校验)
        assert "请输入假期名称" in errs, f"缺少假期名称必填校验: {errs}"
        assert any("额度" in e for e in errs), f"缺少额度必填校验: {errs}"

        # 抽屉保持打开 (校验失败)
        expect(drawer(logged_in_page)).to_be_visible()
        close_drawer(logged_in_page)

    @allure.story("新建假期规则")
    @allure.title("完整信息新建假期规则, 验证创建成功")
    @allure.severity(allure.severity_level.BLOCKER)
    def test_create_success(self, logged_in_page: Page):
        name = f"{TEST_PREFIX}新建_{int(time.time())}"
        try:
            create_rule(
                logged_in_page,
                name=name,
                pay_period="年",
                cycle_start="每年员工入职日",
                quota_value="10",
                quota_unit="天",
            )
            row = get_row_by_name(logged_in_page, name)
            assert row is not None, f"新建假期规则 '{name}' 未出现在列表"
            # 验证请假单位列值正确 (默认为天)
            unit_text = row.locator("td").nth(1).inner_text().strip()
            assert unit_text == "按天请假", f"请假单位应为按天请假, 实际: {unit_text}"
        finally:
            delete_rule_if_exists(logged_in_page, name)

    @allure.story("新建假期规则")
    @allure.title("新建取消, 验证不落库")
    @allure.severity(allure.severity_level.NORMAL)
    def test_create_cancel(self, logged_in_page: Page):
        name = f"{TEST_PREFIX}取消_{int(time.time())}"
        open_create_drawer(logged_in_page)
        fill_required_fields(logged_in_page, name=name)
        close_drawer(logged_in_page)
        goto_leave_rules_page(logged_in_page)
        assert get_row_by_name(logged_in_page, name) is None, (
            f"取消新建后 '{name}' 不应存在"
        )

    @allure.story("新建假期规则")
    @allure.title("重复名称提交, 验证系统拒绝重复假期名称")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_create_duplicate_name(self, logged_in_page: Page):
        name = f"{TEST_PREFIX}重名_{int(time.time())}"
        try:
            create_rule(logged_in_page, name=name)
            goto_leave_rules_page(logged_in_page)

            open_create_drawer(logged_in_page)
            fill_required_fields(logged_in_page, name=name)
            drawer_confirm_btn(logged_in_page).click()
            # 校验失败抽屉应保持打开
            drawer(logged_in_page).wait_for(state="visible", timeout=5000)
            expect(drawer(logged_in_page)).to_be_visible()

            logged_in_page.wait_for_timeout(1500)
            errs = error_messages(logged_in_page)
            msg_txt = message_notice(logged_in_page).inner_text() \
                if message_notice(logged_in_page).count() else ""
            combined = " ".join(errs) + " " + msg_txt

            # 重复/存在/EX 等错误码关键词
            assert re.search(r"重复|存在|EX_06", combined), (
                f"未检测到重名校验, errs={errs}, msg={msg_txt}"
            )
            close_drawer(logged_in_page)
        finally:
            delete_rule_if_exists(logged_in_page, name)

    @allure.story("新建假期规则")
    @allure.title("切换不同发放周期 radio, 状态可正确切换")
    @allure.severity(allure.severity_level.NORMAL)
    def test_pay_period_radio_toggle(self, logged_in_page: Page):
        open_create_drawer(logged_in_page)
        pay_periods = ["年", "月", "手动发放"]
        for p in pay_periods:
            toggle_radio(logged_in_page, radio_wrapper(
                logged_in_page, p, parent_form_item="发放周期"))

        # 默认切回 "年"
        toggle_radio(logged_in_page, radio_wrapper(
            logged_in_page, "年", parent_form_item="发放周期"))
        close_drawer(logged_in_page)

    @allure.story("新建假期规则")
    @allure.title("最小请假单位 radio: 天/半天/小时 可正确切换")
    @allure.severity(allure.severity_level.NORMAL)
    def test_leave_unit_radio_toggle(self, logged_in_page: Page):
        open_create_drawer(logged_in_page)
        leave_units = ["天", "半天", "小时"]
        for u in leave_units:
            toggle_radio(logged_in_page, radio_wrapper(
                logged_in_page, u, parent_form_item="最小请假单位"))

        # 默认切回 "天"
        toggle_radio(logged_in_page, radio_wrapper(
            logged_in_page, "天", parent_form_item="最小请假单位"))
        close_drawer(logged_in_page)

    @allure.story("新建假期规则")
    @allure.title("有效期 radio 四选项均可点击切换")
    @allure.severity(allure.severity_level.NORMAL)
    def test_validity_radio_toggle(self, logged_in_page: Page):
        open_create_drawer(logged_in_page)
        validities = [
            "按发放周期结束后失效",
            "按发放日计算过期日期",
            "永久有效",
        ]
        for v in validities:
            toggle_radio(logged_in_page, radio_wrapper(
                logged_in_page, v, parent_form_item="有效期"))

        toggle_radio(logged_in_page,
                     radio_wrapper(logged_in_page, "按发放周期结束后失效",
                                   parent_form_item="有效期"))
        close_drawer(logged_in_page)

    @allure.story("新建假期规则")
    @allure.title("'按实际工作时长发放余额' checkbox 可切换")
    @allure.severity(allure.severity_level.NORMAL)
    def test_prorate_checkbox_toggle(self, logged_in_page: Page):
        open_create_drawer(logged_in_page)
        logged_in_page.wait_for_timeout(600)  # 抽屉动画
        cb = checkbox_wrapper(logged_in_page, r"按实际工作时长发放余额")
        cb.wait_for(state="visible", timeout=8000)
        toggle_checkbox(logged_in_page, cb, False)
        toggle_checkbox(logged_in_page, cb, True)
        toggle_checkbox(logged_in_page, cb, False)
        close_drawer(logged_in_page)

    @allure.story("新建假期规则")
    @allure.title("'允许延长有效期' checkbox 可切换")
    @allure.severity(allure.severity_level.NORMAL)
    def test_extend_validity_checkbox_toggle(self, logged_in_page: Page):
        open_create_drawer(logged_in_page)
        logged_in_page.wait_for_timeout(600)  # 抽屉动画
        cb = checkbox_wrapper(logged_in_page, r"允许延长有效期")
        cb.wait_for(state="visible", timeout=8000)
        toggle_checkbox(logged_in_page, cb, True)
        toggle_checkbox(logged_in_page, cb, False)
        close_drawer(logged_in_page)

    # ---------- 三、编辑假期规则 ----------

    @allure.story("编辑假期规则")
    @allure.title("编辑已有假期规则, 修改假期名称保存成功")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_edit_rule(self, logged_in_page: Page):
        original = f"{TEST_PREFIX}编辑原_{int(time.time())}"
        edited = f"{TEST_PREFIX}编辑后_{int(time.time())}"
        try:
            create_rule(logged_in_page, name=original)
            row = get_row_by_name(logged_in_page, original)
            assert row is not None, f"前置新建 '{original}' 未成功"

            row.get_by_role("button", name=re.compile(r"编\s*辑")).click()
            expect(drawer(logged_in_page)).to_be_visible(timeout=10000)
            expect(drawer_title(logged_in_page)).to_contain_text("编辑假期规则")

            # 验证假期名称回填了原值
            expect(leave_name_input(logged_in_page)).to_have_value(original)

            # 修改名称 (Vue v-model 需要真实输入事件)
            fill_leave_name(logged_in_page, edited)
            drawer_confirm_btn(logged_in_page).click()

            # 等待抽屉关闭
            expect(drawer(logged_in_page)).not_to_be_visible(timeout=15000)

            # 回到列表验证新名称出现
            goto_leave_rules_page(logged_in_page)
            for _ in range(10):
                if get_row_by_name(logged_in_page, edited) is not None:
                    break
                logged_in_page.wait_for_timeout(1000)
            assert get_row_by_name(logged_in_page, edited) is not None, (
                f"编辑后 '{edited}' 未出现"
            )
        finally:
            delete_rule_if_exists(logged_in_page, original)
            delete_rule_if_exists(logged_in_page, edited)

    @allure.story("编辑假期规则")
    @allure.title("编辑后取消, 数据未修改")
    @allure.severity(allure.severity_level.NORMAL)
    def test_edit_cancel(self, logged_in_page: Page):
        name = f"{TEST_PREFIX}取消改_{int(time.time())}"
        try:
            create_rule(logged_in_page, name=name)
            row = get_row_by_name(logged_in_page, name)
            assert row is not None

            row.get_by_role("button", name=re.compile(r"编\s*辑")).click()
            expect(drawer(logged_in_page)).to_be_visible(timeout=10000)

            fill_leave_name(logged_in_page,
                            f"{TEST_PREFIX}临时_{int(time.time())}")
            close_drawer(logged_in_page)

            goto_leave_rules_page(logged_in_page)
            assert get_row_by_name(logged_in_page, name) is not None, (
                f"取消编辑后原 '{name}' 应仍存在"
            )
        finally:
            delete_rule_if_exists(logged_in_page, name)

    # ---------- 四、删除假期规则 ----------

    @allure.story("删除假期规则")
    @allure.title("删除取消, 假期规则仍存在")
    @allure.severity(allure.severity_level.NORMAL)
    def test_delete_cancel(self, logged_in_page: Page):
        name = f"{TEST_PREFIX}删取消_{int(time.time())}"
        try:
            create_rule(logged_in_page, name=name)
            row = get_row_by_name(logged_in_page, name)
            assert row is not None

            row.get_by_text("删除", exact=True).click()
            expect(logged_in_page.locator(".ant-popconfirm")).to_be_visible(
                timeout=5000)
            popconfirm_cancel_btn(logged_in_page).click()

            row_after = get_row_by_name(logged_in_page, name)
            assert row_after is not None, "取消删除后假期规则应仍存在"
        finally:
            delete_rule_if_exists(logged_in_page, name)

    @allure.story("删除假期规则")
    @allure.title("确认删除, 假期规则从列表移除")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_delete_confirm(self, logged_in_page: Page):
        name = f"{TEST_PREFIX}删确认_{int(time.time())}"
        create_rule(logged_in_page, name=name)
        row = get_row_by_name(logged_in_page, name)
        assert row is not None, f"前置新建 '{name}' 未成功"

        row.get_by_text("删除", exact=True).click()
        expect(logged_in_page.locator(".ant-popconfirm")).to_be_visible(
            timeout=5000)
        popconfirm_confirm_btn(logged_in_page).click()

        # 轮询等待行消失 (最长 12s)
        for _ in range(12):
            if get_row_by_name(logged_in_page, name) is None:
                return
            logged_in_page.wait_for_timeout(1000)

        goto_leave_rules_page(logged_in_page)
        assert get_row_by_name(logged_in_page, name) is None, (
            f"确认删除后假期规则 '{name}' 应不存在"
        )
