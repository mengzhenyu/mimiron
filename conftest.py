import pytest

def pytest_configure(config):
    config.option.allure_report_dir = 'allure-results'
    config.option.allure_report_language = 'zh-CN'  # 新增语言配置