import pytest
import requests
import allure


@allure.parent_suite("父级测试套件")
@allure.suite("自定义测试套件")
@allure.story("示例测试用例")
class TestDemo:
    @allure.title("HTTP状态码验证")
    def test_status_code(self):
        with allure.step("发起GET请求"):
            response = requests.get("https://httpbin.org/status/200")
        assert response.status_code == 200

    # @allure.title("响应内容验证")
    # def test_response_content(self):
    #     with allure.step("发起POST请求"):
    #         response = requests.post("https://httpbin.org/post", json={'key': 'value'})
    #     assert response.json()['data'] == 'key=value'