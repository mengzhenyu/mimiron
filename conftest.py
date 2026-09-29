import pytest
import allure
from playwright.sync_api import Page


def pytest_configure(config):
    config.option.allure_report_dir = 'allure-results'
    config.option.allure_report_language = 'zh-CN'  # 新增语言配置


# ==================== 失败用例自动截图 + 错误原因记录 ====================
# 机制说明:
#   1. 功能BUG导致用例失败时, 自动截取页面快照并附加到 allure 报告;
#   2. 自动捕获失败原因 (异常类型 + 异常信息 + 完整堆栈), 附加到 allure 报告;
#   3. pytest 默认行为即: 单个用例失败不阻塞后续用例执行, 无需额外处理.
#      session 级 page 在失败后可能处于异常状态, reset_to_workbench fixture
#      会自动导航回 /dashboard 恢复初始状态, 确保后续用例正常执行.

@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item):
    """
    pytest hook: 在用例执行完成后生成报告.
    仅在 call 阶段 (非 setup/teardown) 失败时触发截图和错误记录.
    使用 tryfirst=True 确保在 allure-pytest 的 hook 之前执行,
    保证 allure.attach 能正确关联到当前测试上下文.
    """
    outcome = yield
    report = outcome.get_result()

    # 仅处理 call 阶段的失败 (实际测试逻辑执行失败, 非 fixture 失败)
    if report.when == "call" and report.failed:
        # 从用例 fixture 中获取 page 对象 (logged_in_page fixture)
        page = None
        try:
            page = item.funcargs.get("logged_in_page")
        except Exception:
            pass

        # ===== 1. 截取失败时页面快照 =====
        if page is not None and isinstance(page, Page):
            try:
                # 截取全页面快照
                screenshot = page.screenshot(full_page=True)
                allure.attach(
                    screenshot,
                    name=f"失败截图-{item.name}",
                    attachment_type=allure.attachment_type.PNG,
                )
            except Exception:
                pass  # 截图失败不影响报告生成

            try:
                # 附加失败时的页面 URL, 便于定位
                current_url = page.url
                allure.attach(
                    f"失败时URL: {current_url}",
                    name="失败时页面地址",
                    attachment_type=allure.attachment_type.TEXT,
                )
            except Exception:
                pass

        # ===== 2. 记录失败原因 (异常类型 + 异常信息 + 完整堆栈) =====
        try:
            # 从 report.longrepr 中提取失败信息
            # report.longrepr 可能是: ExceptionInfo / ReprFileLocation / str / tuple
            failure_lines = []
            failure_lines.append(f"失败用例: {item.name}")
            failure_lines.append(f"失败阶段: {report.when}")
            failure_lines.append("")

            # 获取异常信息
            if report.longrepr:
                # 将 longrepr 转为字符串, 包含完整的堆栈跟踪和异常信息
                longrepr_str = str(report.longrepr)
                failure_lines.append("===== 失败原因 / 完整堆栈 =====")
                failure_lines.append(longrepr_str)
            else:
                failure_lines.append("失败原因: 未知 (report.longrepr 为空)")

            failure_summary = "\n".join(failure_lines)

            allure.attach(
                failure_summary,
                name="失败原因分析",
                attachment_type=allure.attachment_type.TEXT,
            )
        except Exception:
            pass
