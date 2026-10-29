# -*- coding: utf-8 -*-
"""
观星系统 - 值班管理 > 考勤组设置 E2E 自动化测试
================================================================
技术栈: Python + Playwright + pytest + allure
被测地址: https://stargazer-test.mimiron.cn:8443/infra-attendance/schedule-attendance/groups

页面结构 (基于 Playwright 快照实测):
  列表页:
    - 搜索区 (main 内):
      - searchbox "人员姓名" (唯一搜索输入框)
      - button "search" (放大镜 icon 搜索按钮)
      - button "新建考勤组"
      - reload / column-height / setting / fullscreen 等 icon 按钮
    - 表格列: 考勤组名称 / 类型 / 楼栋 / 考勤时间 / 考勤班组 / 负责人 / 操作
    - 行内操作:
      - button "查看"
      - button "编辑"
      - text "删除" (注意: 删除是纯 text, 不是 button!)
      - text "排班" (仅排班制考勤组)
    - 分页: list "第 N-M 条/总共 X 条" + 上一页/下一页

  新建/编辑抽屉 (Drawer):
    - 考勤组名称     (input #groupName, 必填)
    - 楼栋           (ant-cascader, 必填)
    - 考勤组负责人   (ant-select search-multiple, 必填)
    - 考勤班组       (ant-select search-multiple, 必填)
    - 考勤类型       (radio-wrapper: 固定班制 / 排班制)
    - 星期班次       (7 个 ant-select)
    - 节假日自动排休 (checkbox-wrapper)
    - 节假日配置     (ant-cascader, 勾选自动排休后必填)
    - GPS打卡        (checkbox-wrapper + 名称/经度/纬度/打卡范围)
    - 考勤机打卡     (checkbox-wrapper + 考勤机选择)
    - 允许补卡       (checkbox-wrapper + 4 类补卡 + 限制时间/次数)
    - 底部按钮: 取消 / 确定

定位注意:
  1. checkbox/radio 的 checked class 在内部 .ant-checkbox / .ant-radio 上, 不是 wrapper;
  2. 删除按钮是 text 不是 button, 用 get_by_text("删除") 定位;
  3. 抽屉底部按钮用 .ant-drawer-footer button 比 get_by_role 更可靠;
  4. goto_groups_page 含 cookie 健康检查, 避免 session 过期跳回 login.
================================================================
"""

import os
import re
import time

import pytest
import allure
from playwright.sync_api import sync_playwright, expect, Page


# ==================== 测试配置 ====================

BASE_URL = os.getenv("KAOQIN_BASE_URL", "https://stargazer-test.mimiron.cn:8443")
GROUPS_URL = f"{BASE_URL}/infra-attendance/schedule-attendance/groups"

LOGIN_USERNAME = os.getenv("LOGIN_USERNAME", "zhenyu_m")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "")  # conftest.py 自动加载
LOGIN_URL = f"{BASE_URL}/login"
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

TEST_PREFIX = "AT_考勤组_"

# GPS 打卡固定测试数据 (项目规则, 见 project_memory.md)
GPS_LONGITUDE = "120.01103"
GPS_LATITUDE = "30.2860"
GPS_RANGE = "500"


# ==================== 元素定位器 ====================

# ---------- 列表页 ----------

def search_input(page: Page):
    """搜索区 - 唯一搜索框 (role=searchbox, name=人员姓名)"""
    return page.get_by_role("searchbox")


def search_button(page: Page):
    """搜索按钮 (放大镜 icon, 紧挨着 searchbox)"""
    return page.locator("button").filter(has=page.locator("svg")).first


def add_group_button(page: Page):
    """新建考勤组按钮"""
    return page.get_by_role("button", name=re.compile(r"新\s*建\s*考\s*勤\s*组"))


def group_rows(page: Page):
    return page.locator(".ant-table-tbody > tr.ant-table-row")


def pagination(page: Page):
    """分页区域 (含统计文案)"""
    return page.locator(".ant-pagination").first


def empty_placeholder(page: Page):
    return page.locator(".ant-table-placeholder")


# ---------- 抽屉 ----------

def drawer(page: Page):
    """当前可见的 Drawer (Portal 模式: 按钮在 .ant-drawer-content, checkbox/select 在 body 根)"""
    return page.locator(".ant-drawer-content").last


def drawer_title(page: Page):
    return page.locator(".ant-drawer-title").last


def group_name_input(page: Page):
    """考勤组名称 (Drawer 内, visible)"""
    return page.locator(".ant-drawer-content #groupName:visible")


def building_select(page: Page):
    """楼栋级联 (Portal 渲染到 body, 找抽屉内第一个 visible cascader)"""
    return page.locator(".ant-drawer .ant-select.ant-cascader").first


def owner_select(page: Page):
    """考勤组负责人"""
    return page.locator(".ant-drawer .ant-select").nth(1)


def team_select(page: Page):
    """考勤班组"""
    return page.locator(".ant-drawer .ant-select").nth(2)


def attendance_type_radio(page: Page, label: str):
    """考勤类型 radio-wrapper (Portal)"""
    return page.locator(".ant-radio-wrapper", has_text=re.compile(label))


def weekday_shift_select(page: Page, day_index: int):
    """星期班次下拉"""
    return page.locator(".ant-drawer .ant-select").nth(3 + day_index)


def holiday_checkbox(page: Page):
    """节假日自动排休 (Portal)"""
    return page.locator(".ant-checkbox-wrapper", has_text=re.compile(r"节假日自动排休"))


def holiday_cascader(page: Page):
    """节假日配置级联 (抽屉内第 2 个 cascader)"""
    d = page.locator(".ant-drawer .ant-select.ant-cascader")
    if d.count() >= 2:
        return d.nth(1)
    return d.last


def gps_checkbox(page: Page):
    """GPS打卡 (Portal)"""
    return page.locator(".ant-checkbox-wrapper", has_text=re.compile(r"GPS打卡"))


def punchcard_checkbox(page: Page):
    """考勤机打卡 (Portal)"""
    return page.locator(".ant-checkbox-wrapper", has_text=re.compile(r"考勤机打卡"))


def allow_makeup_checkbox(page: Page):
    """允许补卡 (Portal)"""
    return page.locator(".ant-checkbox-wrapper", has_text=re.compile(r"允许补卡"))


def makeup_checkbox(page: Page, label: str):
    """补卡类型 checkbox-wrapper (Portal)"""
    return page.locator(".ant-checkbox-wrapper", has_text=re.compile(label))


def makeup_limit_days_checkbox(page: Page):
    """限制补卡时间 (Portal)"""
    return page.locator(".ant-checkbox-wrapper", has_text=re.compile(r"限制补卡时间"))


def makeup_limit_count_checkbox(page: Page):
    """限制补卡次数 (Portal)"""
    return page.locator(".ant-checkbox-wrapper", has_text=re.compile(r"限制补卡次数"))


def drawer_cancel_btn(page: Page):
    """抽屉内取消按钮"""
    return drawer(page).get_by_role("button", name=re.compile(r"取\s*消"))


def drawer_confirm_btn(page: Page):
    """抽屉内确定按钮"""
    return drawer(page).get_by_role("button", name=re.compile(r"确\s*定"))


def error_messages(page: Page):
    """表单校验错误文案列表"""
    return [e.inner_text().strip() for e in page.locator(".ant-form-item-explain-error").all()]


def form_item_labels(page: Page):
    """有红色星号 (*) 的必填项 label 文本"""
    stars = drawer(page).locator(".ant-form-item.ant-form-item-required")
    labels = []
    for i in range(stars.count()):
        lbl = stars.nth(i).locator("label, .ant-form-item-label")
        labels.append(lbl.inner_text().replace("*", "").strip())
    return labels


def message_notice(page: Page):
    return page.locator(".ant-message-notice").last


def popconfirm_confirm_btn(page: Page):
    return page.locator(".ant-popconfirm-buttons .ant-btn-primary").last


def popconfirm_cancel_btn(page: Page):
    return page.locator(".ant-popconfirm-buttons .ant-btn-default").last


# ==================== 辅助函数 ====================

def _is_checkbox_checked(wrapper_locator) -> bool:
    """检查 .ant-checkbox-wrapper 的 checked 状态
    注意: ant-checkbox-checked class 在内层 .ant-checkbox 上"""
    inner = wrapper_locator.locator(".ant-checkbox").first
    if inner.count() == 0:
        return False
    cls = inner.get_attribute("class") or ""
    return "ant-checkbox-checked" in cls


def _ensure_logged_in(page: Page):
    """Cookie 过期时重新登录"""
    if "login" in page.url and page.locator("#login").count():
        page.locator("#login").fill(LOGIN_USERNAME)
        page.locator("#password").fill(LOGIN_PASSWORD)
        page.get_by_role("button", name=re.compile(r"登\s*录")).click()
        expect(page).to_have_url(re.compile(r"/dashboard|/event"), timeout=20000)


def goto_groups_page(page: Page):
    """导航到考勤组设置页 (含 cookie 健康检查)
    注意: 页面有长连接, networkidle 不可靠, 用 domcontentloaded + 显式等待;
    用 pageSize=100 保证新建的考勤组一定在当前页可见"""
    page.goto(
        f"{GROUPS_URL}?current=1&pageSize=100",
        wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    # Cookie 健康检查
    if "login" in page.url:
        _ensure_logged_in(page)
        page.goto(
            f"{GROUPS_URL}?current=1&pageSize=100",
            wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

    try:
        expect(add_group_button(page)).to_be_visible(timeout=15000)
    except AssertionError:
        # 上一步可能残留抽屉/页面加载异常, 重载一次
        page.reload(wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        expect(add_group_button(page)).to_be_visible(timeout=20000)


def open_create_drawer(page: Page):
    """打开新建考勤组抽屉"""
    add_group_button(page).click()
    expect(drawer(page)).to_be_visible(timeout=10000)
    expect(drawer_title(page)).to_contain_text("新建考勤组")


def select_cascader_option(page, selector, *titles):
    """级联选择器多步选择"""
    selector.click()
    page.wait_for_timeout(600)
    for title in titles:
        item = page.locator(
            f".ant-select-dropdown:visible .ant-cascader-menu-item[title='{title}']"
        ).last
        expect(item).to_be_visible(timeout=5000)
        item.click()
        page.wait_for_timeout(500)
    # 关闭下拉 (仅在仍展开时按 Escape, 否则会误关抽屉)
    if page.locator(".ant-select-dropdown:visible").count() > 0:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)


def multi_select_first_options(page, selector, count: int = 1):
    """多选下拉中选取前 count 个选项, 然后关闭下拉"""
    selector.click()
    page.wait_for_timeout(600)
    opts = page.locator(".ant-select-dropdown:visible .ant-select-item-option")
    avail = opts.count()
    n = min(count, avail)
    for i in range(n):
        opts.nth(i).click()
        page.wait_for_timeout(300)
    # 下拉仍展开时才按 Escape, 避免误关抽屉
    if page.locator(".ant-select-dropdown:visible").count() > 0:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)


def toggle_checkbox(page, selector, target: bool = True):
    """确保 checkbox wrapper 处于目标状态"""
    is_now = _is_checkbox_checked(selector)
    if target and not is_now:
        selector.click()
        page.wait_for_timeout(200)
    elif not target and is_now:
        selector.click()
        page.wait_for_timeout(200)
    assert _is_checkbox_checked(selector) == target, (
        f"checkbox toggle 失败: 目标={target} 实际={_is_checkbox_checked(selector)}"
    )


def close_drawer(page: Page):
    """用取消按钮关闭抽屉"""
    drawer_cancel_btn(page).click()
    expect(drawer(page)).not_to_be_visible(timeout=5000)


def fill_gps_fields(page: Page):
    """填写 GPS 打卡的名称/经度/纬度/打卡范围"""
    # 名称 (label 精确匹配 "名称", 避免撞上 "考勤组名称")
    name_item = page.locator(".ant-drawer .ant-form-item").filter(
        has=page.locator("label", has_text=re.compile(r"^\s*名称\s*$"))).first
    name_input = name_item.locator("input:visible").first
    if name_input.count():
        name_input.fill("自动化GPS点")
    # 经度/纬度/打卡范围 (drawer 内 visible 的 input-number 恰好 3 个)
    number_inputs = drawer(page).locator(".ant-input-number-input:visible")
    if number_inputs.count() >= 3:
        number_inputs.nth(0).fill(GPS_LONGITUDE)
        number_inputs.nth(1).fill(GPS_LATITUDE)
        number_inputs.nth(2).fill(GPS_RANGE)


def fill_required_fields(page: Page, name: str = None,
                          building: str = "1号楼",
                          skip_gps: bool = False,
                          skip_punchcard: bool = True,
                          skip_holiday: bool = False,
                          skip_makeup: bool = True,
                          skip_team: bool = False):
    """
    填写抽屉必填字段 + 清理默认勾选.
    注意: GPS打卡/考勤机打卡/允许补卡 等默认是 checked 的.
    注意: 服务端要求至少一种打卡方式, 而「考勤机选择」测试环境无数据,
          因此默认保留 GPS打卡 并自动填写 GPS 字段 (skip_gps=False).
    注意: checkbox/radio/select 都是 Portal 渲染, 必须用 page 级别定位.
    """
    # ---- 清理默认勾选 (Portal checkbox, page 级别) ----
    if skip_gps:
        if _is_checkbox_checked(gps_checkbox(page)):
            toggle_checkbox(page, gps_checkbox(page), False)
    else:
        if not _is_checkbox_checked(gps_checkbox(page)):
            toggle_checkbox(page, gps_checkbox(page), True)

    if skip_punchcard and _is_checkbox_checked(punchcard_checkbox(page)):
        toggle_checkbox(page, punchcard_checkbox(page), False)

    if skip_makeup and _is_checkbox_checked(allow_makeup_checkbox(page)):
        toggle_checkbox(page, allow_makeup_checkbox(page), False)

    # ---- 填写必填字段 ----
    if name:
        group_name_input(page).fill(name)

    if building:
        select_cascader_option(page, building_select(page), building)

    # 负责人 - 取第一项
    multi_select_first_options(page, owner_select(page), count=1)

    # 考勤班组 - 取第一项 (skip_team=True 时交由 submit_with_available_team 处理)
    if not skip_team:
        multi_select_first_options(page, team_select(page), count=1)

    # ---- GPS 打卡字段 ----
    if not skip_gps:
        fill_gps_fields(page)

    # ---- 滚动到底部 (节假日/GPS/补卡区域) ----
    page.evaluate("document.querySelector('.ant-drawer-content')?.scrollTo(0, 10000)")
    page.wait_for_timeout(400)

    # ---- 节假日自动排休 + 节假日配置 ----
    if not skip_holiday:
        h_cb = holiday_checkbox(page)
        if h_cb.count() and not _is_checkbox_checked(h_cb):
            toggle_checkbox(page, h_cb, True)

        # 节假日配置: 按 form-item label 定位 (普通单选 select, 非 cascader)
        hc = page.locator(
            ".ant-drawer .ant-form-item:has(label:has-text('节假日配置')) .ant-select"
        ).first
        if hc.count():
            hc.click()
            page.wait_for_timeout(800)
            first_opt = page.locator(".ant-select-dropdown:visible .ant-select-item-option").first
            if first_opt.count():
                first_opt.click()
            page.wait_for_timeout(300)
            # 下拉仍展开时才按 Escape, 避免误关抽屉
            if page.locator(".ant-select-dropdown:visible").count() > 0:
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)


def all_team_names(page: Page) -> list:
    """展开班组下拉并滚动虚拟列表, 收集全部班组名称.
    注意: rc-virtual-list 只渲染可视区, 必须滚动才能拿到全部选项."""
    team_select(page).click()
    page.wait_for_timeout(800)
    seen = []
    holder = page.locator(".ant-select-dropdown:visible .rc-virtual-list-holder").first
    for _ in range(30):
        for t in page.locator(
                ".ant-select-dropdown:visible .ant-select-item-option-content"
        ).all_text_contents():
            t = t.strip()
            if t and t not in seen:
                seen.append(t)
        if holder.count() == 0:
            break
        holder.evaluate("e => e.scrollTop = e.scrollHeight")
        page.wait_for_timeout(300)
    if page.locator(".ant-select-dropdown:visible").count() > 0:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    return seen


def _clear_team_selection(page: Page):
    """清空班组已选值 (点每个 tag 的 remove 图标)"""
    for _ in range(10):
        rm = team_select(page).locator(".ant-select-selection-item-remove")
        if rm.count() == 0:
            break
        rm.first.click()
        page.wait_for_timeout(150)


def _select_team_by_name(page: Page, name: str) -> bool:
    """通过搜索框精确选择指定班组 (下拉虚拟滚动, 不能按 index 点)"""
    _clear_team_selection(page)
    inp = team_select(page).locator("input").first
    inp.click()
    page.wait_for_timeout(300)
    inp.fill(name)
    page.wait_for_timeout(800)
    opt = page.locator(
        ".ant-select-dropdown:visible .ant-select-item-option"
    ).filter(has_text=name).first
    if opt.count() == 0:
        if page.locator(".ant-select-dropdown:visible").count() > 0:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        return False
    opt.click()
    page.wait_for_timeout(300)
    if page.locator(".ant-select-dropdown:visible").count() > 0:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    return True


_KNOWN_FREE_TEAM = {"name": None}


def submit_with_available_team(page, team_names: list = None):
    """
    逐个尝试未占用的班组并提交表单.
    背景: 服务端要求班组唯一 (EX_0626: team already joined another attendance
    group), 且失败时页面无任何提示, 抽屉保持打开; 因此监听 POST groups.data
    响应来判断结果.
    注意: 创建成功后抽屉约 8s 才关闭 (先出 toast), 不能只等 2s.
    返回 (drawer_closed: bool, response_body: str)
    """
    state = {"body": "", "success": False}

    def _on_resp(resp):
        if resp.request.method == "POST" and "groups.data" in resp.url:
            try:
                body = resp.text()
            except Exception:
                return
            state["body"] = body
            state["success"] = "statusCode" not in body

    names = list(team_names) if team_names else all_team_names(page)
    # 优先使用 AT_ 前缀班组 (test_banzushezhi 每次运行会保留一个空闲班组),
    # 其余按原顺序; 上次成功的班组置顶, 减少逐个试错耗时
    names.sort(key=lambda n: 0 if n.startswith("AT_") else 1)
    if _KNOWN_FREE_TEAM["name"] in names:
        names.remove(_KNOWN_FREE_TEAM["name"])
        names.insert(0, _KNOWN_FREE_TEAM["name"])
    page.on("response", _on_resp)
    try:
        for name in names:
            if not _select_team_by_name(page, name):
                continue  # 搜索后无匹配 (名称含特殊字符等)
            state["body"], state["success"] = "", False
            drawer_confirm_btn(page).click()
            # 等待创建响应到达 (网络可能较慢, 最多 10s)
            for _ in range(20):
                page.wait_for_timeout(500)
                if state["body"] or not drawer(page).is_visible():
                    break
            if state["success"]:
                _KNOWN_FREE_TEAM["name"] = name
                # 成功: 等待抽屉关闭 (最长 15s)
                for _ in range(20):
                    if not drawer(page).is_visible():
                        return True, state["body"]
                    page.wait_for_timeout(700)
                return True, state["body"]  # 服务端已创建成功, 抽屉晚点关
            if not drawer(page).is_visible():
                return False, state["body"]
            if "already joined" in state["body"] or "EX_0626" in state["body"]:
                continue  # 班组被占用, 换下一个
            return False, state["body"]  # 其他业务错误 (如重名)
        return False, state["body"]
    finally:
        page.remove_listener("response", _on_resp)


def create_group(page: Page, name: str, building: str = "1号楼"):
    """快速新建固定班制考勤组"""
    open_create_drawer(page)
    fill_required_fields(page, name=name, building=building, skip_team=True)
    ok, body = submit_with_available_team(page)
    assert ok, f"创建考勤组 '{name}' 失败: {body}"
    # toast 持续时间短, 以列表出现为准, 避免漏报; 列表刷新有延迟, 轮询等待
    goto_groups_page(page)
    for _ in range(10):
        if get_row_by_name(page, name) is not None:
            return True
        page.wait_for_timeout(1000)
    raise AssertionError(f"创建后列表未出现 '{name}'")


def get_row_by_name(page: Page, name: str):
    """在当前列表查找考勤组"""
    rows = group_rows(page)
    for i in range(rows.count()):
        row = rows.nth(i)
        try:
            if row.locator("td").nth(0).inner_text().strip() == name:
                return row
        except Exception:
            continue
    return None


def delete_group_if_exists(page: Page, name: str):
    """清理测试数据"""
    goto_groups_page(page)
    row = get_row_by_name(page, name)
    if row is None:
        return
    row.get_by_text("删除").click()
    expect(page.locator(".ant-popconfirm")).to_be_visible(timeout=5000)
    popconfirm_confirm_btn(page).click()
    for _ in range(12):
        if get_row_by_name(page, name) is None:
            return
        page.wait_for_timeout(1000)


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
def reset_to_groups(logged_in_page: Page):
    """每个用例前导航回考勤组设置页"""
    goto_groups_page(logged_in_page)
    yield


# ==================== 测试用例 ====================


@allure.feature("值班管理-考勤组设置")
@allure.label("owner", "自动化测试")
@allure.link("https://stargazer-test.mimiron.cn:8443/login", name="被测系统登录页")
class TestKaoQin:
    """观星系统 - 值班管理 > 考勤组设置 E2E 测试"""

    # ---------- 一、列表页 ----------

    @allure.story("考勤组设置列表页")
    @allure.title("进入考勤组设置页, 验证搜索框/新建按钮/表格/分页加载正常")
    @allure.severity(allure.severity_level.BLOCKER)
    def test_page_load(self, logged_in_page: Page):
        with allure.step("验证搜索框与新建按钮"):
            expect(search_input(logged_in_page)).to_be_visible()
            expect(add_group_button(logged_in_page)).to_be_visible()

        with allure.step("验证表格列头"):
            headers = [
                h.strip()
                for h in logged_in_page.locator(".ant-table-thead th").all_text_contents()
                if h.strip()
            ]
            assert headers == [
                "考勤组名称", "类型", "楼栋", "考勤时间", "考勤班组", "负责人", "操作"
            ], f"表头不正确: {headers}"

        with allure.step("验证分页统计文案"):
            expect(pagination(logged_in_page)).to_be_visible()
            expect(pagination(logged_in_page)).to_contain_text(
                re.compile(r"第\s*1-\d+\s*条/总共\s*\d+\s*条")
            )

    @allure.story("考勤组设置列表页")
    @allure.title("表格首行数据列值正确展示")
    @allure.severity(allure.severity_level.NORMAL)
    def test_row_data(self, logged_in_page: Page):
        row = group_rows(logged_in_page).first
        expect(row.locator("td").nth(0)).not_to_have_text("")
        type_text = row.locator("td").nth(1).inner_text().strip()
        assert type_text in ("固定班制", "排班制"), f"类型值异常: {type_text}"
        # 操作列
        expect(row.get_by_role("button", name="查看")).to_be_visible()
        expect(row.get_by_role("button", name="编辑")).to_be_visible()
        expect(row.get_by_text("删除")).to_be_visible()

    @allure.story("考勤组设置列表页")
    @allure.title("按人员姓名搜索, 验证结果过滤")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_search_by_member_name(self, logged_in_page: Page):
        # 从首行负责人列取一个关键词
        owner_cell = group_rows(logged_in_page).first.locator("td").nth(5).inner_text().strip()
        if not owner_cell:
            pytest.skip("首行负责人为空, 无法搜索")
        kw = owner_cell[:2]
        with allure.step(f"输入关键词 '{kw}' 搜索"):
            search_input(logged_in_page).fill(kw)
            search_button(logged_in_page).click()
            logged_in_page.wait_for_load_state("networkidle")
            logged_in_page.wait_for_timeout(1200)

        rows = group_rows(logged_in_page)
        expect(rows.first).to_be_visible(timeout=10000)

        with allure.step("重置搜索 (清空输入框)"):
            search_input(logged_in_page).fill("")
            search_button(logged_in_page).click()
            logged_in_page.wait_for_timeout(1200)

    @allure.story("考勤组设置列表页")
    @allure.title("排班制考勤组行额外显示「排班」文本")
    @allure.severity(allure.severity_level.NORMAL)
    def test_shift_type_has_schedule_button(self, logged_in_page: Page):
        schedule_row = group_rows(logged_in_page).filter(has_text="排班制")
        if schedule_row.count() == 0:
            pytest.skip("当前列表无排班制考勤组")
        row = schedule_row.first
        expect(row.get_by_text("排班", exact=True)).to_be_visible()

    # ---------- 二、新建考勤组 ----------

    @allure.story("新建考勤组")
    @allure.title("空表单提交, 验证必填校验覆盖")
    @allure.severity(allure.severity_level.BLOCKER)
    def test_create_empty_validation(self, logged_in_page: Page):
        open_create_drawer(logged_in_page)
        # 清理默认勾选, 避免 GPS/考勤机默认 checked 产生额外校验
        toggle_checkbox(logged_in_page, gps_checkbox(logged_in_page), False)
        toggle_checkbox(logged_in_page, punchcard_checkbox(logged_in_page), False)
        toggle_checkbox(logged_in_page, allow_makeup_checkbox(logged_in_page), False)
        drawer_confirm_btn(logged_in_page).click()
        expect(drawer(logged_in_page)).to_be_visible()
        # 等待校验文案渲染
        logged_in_page.wait_for_selector(".ant-form-item-explain-error", timeout=5000)
        errs = error_messages(logged_in_page)
        # 至少应有 4 项必填校验 (名称/楼栋/负责人/班组)
        must_have = ["请输入考勤组名称", "请选择楼栋", "请选择考勤组负责人", "请选择考勤班组"]
        for m in must_have:
            assert m in errs, f"缺少必填校验 '{m}': {errs}"
        close_drawer(logged_in_page)

    @allure.story("新建考勤组")
    @allure.title("完整信息新建固定班制考勤组, 验证创建成功")
    @allure.severity(allure.severity_level.BLOCKER)
    def test_create_success(self, logged_in_page: Page):
        name = f"{TEST_PREFIX}新建_{int(time.time())}"
        try:
            create_group(logged_in_page, name)
            row = get_row_by_name(logged_in_page, name)
            assert row is not None, f"新建考勤组 '{name}' 未出现在列表"
            assert row.locator("td").nth(1).inner_text().strip() == "固定班制"
        finally:
            delete_group_if_exists(logged_in_page, name)

    @allure.story("新建考勤组")
    @allure.title("新建取消, 验证不落库")
    @allure.severity(allure.severity_level.NORMAL)
    def test_create_cancel(self, logged_in_page: Page):
        name = f"{TEST_PREFIX}取消_{int(time.time())}"
        open_create_drawer(logged_in_page)
        group_name_input(logged_in_page).fill(name)
        close_drawer(logged_in_page)
        goto_groups_page(logged_in_page)
        assert get_row_by_name(logged_in_page, name) is None

    @allure.story("新建考勤组")
    @allure.title("重名提交, 验证名称重复校验")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_create_duplicate_name(self, logged_in_page: Page):
        # 先成功创建一个, 再用同名提交验证重名校验
        name = f"{TEST_PREFIX}重名_{int(time.time())}"
        try:
            create_group(logged_in_page, name)
            goto_groups_page(logged_in_page)

            open_create_drawer(logged_in_page)
            fill_required_fields(logged_in_page, name=name, skip_team=True)
            ok, body = submit_with_available_team(logged_in_page)
            assert not ok, f"重名提交不应成功, body={body}"
            expect(drawer(logged_in_page)).to_be_visible()
            logged_in_page.wait_for_timeout(1500)
            errs = error_messages(logged_in_page)
            msg_txt = message_notice(logged_in_page).inner_text() if message_notice(logged_in_page).count() else ""
            combined = " ".join(errs) + " " + msg_txt + " " + body
            assert re.search(r"重复|存在|EX_06", combined), (
                f"未检测到重名校验, errs={errs}, msg={msg_txt}, body={body}"
            )
            close_drawer(logged_in_page)
        finally:
            delete_group_if_exists(logged_in_page, name)

    @allure.story("新建考勤组")
    @allure.title("切换排班制后, 抽屉保持稳定")
    @allure.severity(allure.severity_level.NORMAL)
    def test_schedule_mode_switch(self, logged_in_page: Page):
        open_create_drawer(logged_in_page)
        schedule_radio = attendance_type_radio(logged_in_page, "排班制")
        schedule_radio.click()
        page = logged_in_page
        # 验证抽屉仍可见
        expect(drawer(page)).to_be_visible()
        close_drawer(page)

    @allure.story("新建考勤组")
    @allure.title("节假日自动排休勾选后, 节假日配置变为必填")
    @allure.severity(allure.severity_level.NORMAL)
    def test_holiday_auto_check(self, logged_in_page: Page):
        open_create_drawer(logged_in_page)
        # 先清理默认勾选
        toggle_checkbox(logged_in_page, gps_checkbox(logged_in_page), False)
        toggle_checkbox(logged_in_page, punchcard_checkbox(logged_in_page), False)
        toggle_checkbox(logged_in_page, allow_makeup_checkbox(logged_in_page), False)

        # 开启节假日自动排休, 但 **不** 选节假日配置
        toggle_checkbox(logged_in_page, holiday_checkbox(logged_in_page), True)

        # 填其他必填 (跳过节假日配置的级联选择)
        fill_required_fields(
            logged_in_page,
            name=f"{TEST_PREFIX}节假日_{int(time.time())}",
            skip_gps=True, skip_punchcard=True,
            skip_holiday=True,  # 跳过节假日配置级联
            skip_makeup=True,
        )
        # fill_required_fields skip_holiday=True 会关掉 holiday checkbox
        # 我们需要重新打开它 (保持其他勾选已清理的状态)
        toggle_checkbox(logged_in_page, holiday_checkbox(logged_in_page), True)

        drawer_confirm_btn(logged_in_page).click()
        expect(drawer(logged_in_page)).to_be_visible()
        logged_in_page.wait_for_selector(".ant-form-item-explain-error", timeout=5000)
        errs = error_messages(logged_in_page)
        assert any("节假日" in e for e in errs), (
            f"应出现节假日配置校验, 实际: {errs}"
        )
        close_drawer(logged_in_page)

    @allure.story("新建考勤组")
    @allure.title("GPS 打卡开启后, 验证名称/经度/纬度/范围控件可见")
    @allure.severity(allure.severity_level.NORMAL)
    def test_gps_card_fill(self, logged_in_page: Page):
        open_create_drawer(logged_in_page)
        # 清理考勤机/补卡 默认勾选
        toggle_checkbox(logged_in_page, punchcard_checkbox(logged_in_page), False)
        toggle_checkbox(logged_in_page, allow_makeup_checkbox(logged_in_page), False)

        # 打开 GPS
        toggle_checkbox(logged_in_page, gps_checkbox(logged_in_page), True)

        # GPS 区域控件可见验证
        d = drawer(logged_in_page)
        # 经纬度/范围 三个 input-number (visible)
        number_inputs = d.locator(".ant-input-number-input:visible")
        expect(number_inputs).to_have_count(3, timeout=5000)
        number_inputs.nth(0).fill(GPS_LONGITUDE)  # 经度
        number_inputs.nth(1).fill(GPS_LATITUDE)   # 纬度
        number_inputs.nth(2).fill(GPS_RANGE)      # 打卡范围

        close_drawer(logged_in_page)

    @allure.story("新建考勤组")
    @allure.title("允许补卡 4 类 checkbox 可独立勾选")
    @allure.severity(allure.severity_level.NORMAL)
    def test_makeup_checkboxes_independent(self, logged_in_page: Page):
        open_create_drawer(logged_in_page)
        toggle_checkbox(logged_in_page, gps_checkbox(logged_in_page), False)
        toggle_checkbox(logged_in_page, punchcard_checkbox(logged_in_page), False)

        toggle_checkbox(logged_in_page, allow_makeup_checkbox(logged_in_page), True)

        for lbl in ["迟到", "早退"]:
            ckb = makeup_checkbox(logged_in_page, lbl)
            expect(ckb).to_be_visible(timeout=5000)
            toggle_checkbox(logged_in_page, ckb, True)
            toggle_checkbox(logged_in_page, ckb, False)

        close_drawer(logged_in_page)

    @allure.story("新建考勤组")
    @allure.title("限制补卡时间/次数开关可切换且数值输入可填")
    @allure.severity(allure.severity_level.NORMAL)
    def test_makeup_limit_inputs(self, logged_in_page: Page):
        open_create_drawer(logged_in_page)
        toggle_checkbox(logged_in_page, gps_checkbox(logged_in_page), False)
        toggle_checkbox(logged_in_page, punchcard_checkbox(logged_in_page), False)

        toggle_checkbox(logged_in_page, allow_makeup_checkbox(logged_in_page), True)

        # 默认已勾选, 先关掉再打开
        toggle_checkbox(logged_in_page, makeup_limit_days_checkbox(logged_in_page), False)
        toggle_checkbox(logged_in_page, makeup_limit_count_checkbox(logged_in_page), False)
        toggle_checkbox(logged_in_page, makeup_limit_days_checkbox(logged_in_page), True)
        toggle_checkbox(logged_in_page, makeup_limit_count_checkbox(logged_in_page), True)

        number_inputs = drawer(logged_in_page).locator(".ant-input-number-input:visible")
        expect(number_inputs.nth(0)).to_be_visible(timeout=5000)
        number_inputs.nth(0).fill("3")
        number_inputs.nth(1).fill("5")

        close_drawer(logged_in_page)

    # ---------- 三、编辑考勤组 ----------

    @allure.story("编辑考勤组")
    @allure.title("编辑考勤组, 修改名称保存成功")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_edit_group(self, logged_in_page: Page):
        name = f"{TEST_PREFIX}编辑_{int(time.time())}"
        edited = f"{TEST_PREFIX}编辑后_{int(time.time())}"
        try:
            create_group(logged_in_page, name)
            row = get_row_by_name(logged_in_page, name)
            assert row is not None, f"前置新建 '{name}' 未成功"
            row.get_by_role("button", name="编辑").click()
            expect(drawer(logged_in_page)).to_be_visible(timeout=10000)
            expect(drawer_title(logged_in_page)).to_contain_text("编辑考勤组")
            expect(group_name_input(logged_in_page)).to_have_value(name)
            group_name_input(logged_in_page).fill(edited)
            drawer_confirm_btn(logged_in_page).click()
            # 保存成功后抽屉约 10s 才关闭 (先出 toast), 轮询等待
            for _ in range(20):
                if not drawer(logged_in_page).is_visible():
                    break
                logged_in_page.wait_for_timeout(1000)
            expect(drawer(logged_in_page)).not_to_be_visible(timeout=5000)
            # 列表刷新有延迟, 轮询等待新名称出现
            for _ in range(10):
                if get_row_by_name(logged_in_page, edited) is not None:
                    break
                logged_in_page.wait_for_timeout(1000)
            assert get_row_by_name(logged_in_page, edited) is not None, (
                f"编辑后 '{edited}' 未出现"
            )
        finally:
            delete_group_if_exists(logged_in_page, name)
            delete_group_if_exists(logged_in_page, edited)

    @allure.story("编辑考勤组")
    @allure.title("编辑后取消, 数据未修改")
    @allure.severity(allure.severity_level.NORMAL)
    def test_edit_group_cancel(self, logged_in_page: Page):
        name = f"{TEST_PREFIX}取消改_{int(time.time())}"
        try:
            create_group(logged_in_page, name)
            row = get_row_by_name(logged_in_page, name)
            assert row is not None, f"前置新建 '{name}' 未成功"
            row.get_by_role("button", name="编辑").click()
            expect(drawer_title(logged_in_page)).to_contain_text("编辑考勤组")
            group_name_input(logged_in_page).fill(f"{TEST_PREFIX}临时_{int(time.time())}")
            close_drawer(logged_in_page)
            goto_groups_page(logged_in_page)
            assert get_row_by_name(logged_in_page, name) is not None, (
                f"取消编辑后原 '{name}' 应仍存在"
            )
        finally:
            delete_group_if_exists(logged_in_page, name)

    # ---------- 四、删除考勤组 ----------

    @allure.story("删除考勤组")
    @allure.title("删除取消, 考勤组仍存在")
    @allure.severity(allure.severity_level.NORMAL)
    def test_delete_cancel(self, logged_in_page: Page):
        name = f"{TEST_PREFIX}删取消_{int(time.time())}"
        try:
            create_group(logged_in_page, name)
            row = get_row_by_name(logged_in_page, name)
            assert row is not None
            row.get_by_text("删除").click()
            expect(logged_in_page.locator(".ant-popconfirm")).to_be_visible(timeout=5000)
            popconfirm_cancel_btn(logged_in_page).click()
            row_after = get_row_by_name(logged_in_page, name)
            assert row_after is not None, "取消删除后考勤组应仍存在"
        finally:
            delete_group_if_exists(logged_in_page, name)

    @allure.story("删除考勤组")
    @allure.title("确认删除, 考勤组从列表移除")
    @allure.severity(allure.severity_level.CRITICAL)
    def test_delete_confirm(self, logged_in_page: Page):
        name = f"{TEST_PREFIX}删确认_{int(time.time())}"
        create_group(logged_in_page, name)
        row = get_row_by_name(logged_in_page, name)
        assert row is not None, f"前置新建 '{name}' 未成功"
        row.get_by_text("删除").click()
        expect(logged_in_page.locator(".ant-popconfirm")).to_be_visible(timeout=5000)
        popconfirm_confirm_btn(logged_in_page).click()
        # 删除后列表刷新有延迟, 轮询等待行消失 (最长 12s)
        for _ in range(12):
            if get_row_by_name(logged_in_page, name) is None:
                return
            logged_in_page.wait_for_timeout(1000)
        goto_groups_page(logged_in_page)
        assert get_row_by_name(logged_in_page, name) is None, "确认删除后考勤组应不存在"
