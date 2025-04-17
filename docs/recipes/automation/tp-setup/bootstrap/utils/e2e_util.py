from urllib.parse import urlparse, parse_qs
import json

class E2EUtils:
    @staticmethod
    def assert_api_request_and_response(
            page,
            base_path: str,
            trigger_fn=None,
            expected_method: str = "GET",
            expected_status: int = 200,
            expected_query_params: dict = None,
            expected_request_json: dict = None,
            expected_response_json: dict = None
    ):
        """
        General-purpose request and response assertion utility.

        :param page: Playwright page object
        :param base_path: Base path of the API request URL
        :param trigger_fn: A function to trigger the request (e.g., a button click)
        :param expected_method: HTTP method such as GET/POST/PUT/DELETE
        :param expected_status: Expected HTTP response status code (default 200)
        :param expected_query_params: Expected query string parameters for GET requests (optional)
        :param expected_request_json: Expected JSON body for POST/PUT requests (optional)
        :param expected_response_json: Expected key-value pairs in JSON response (optional)
        """
        with page.expect_request(lambda req: base_path in req.url) as req_info, \
                page.expect_response(lambda res: base_path in res.url) as res_info:
            trigger_fn()

        request = req_info.value
        response = res_info.value

        # Assert HTTP method
        assert request.method == expected_method.upper(), f"Expected method {expected_method}, got {request.method}"

        # Assert query parameters (for GET requests)
        if expected_query_params:
            parsed_url = urlparse(request.url)
            query = parse_qs(parsed_url.query)
            for key, expected_val in expected_query_params.items():
                if expected_val is None:
                    assert key in query, f"Missing query param: {key}"
                else:
                    assert query.get(key) == [expected_val], f"Query param '{key}' expected '{expected_val}', got '{query.get(key)}'"

        # Assert JSON body parameters (for POST/PUT requests)
        if expected_method.upper() in ("POST", "PUT") and expected_request_json:
            body = request.post_data()
            try:
                json_body = json.loads(body)
                for key, expected_val in expected_request_json.items():
                    assert key in json_body and json_body[key] == expected_val, \
                        f"Body param '{key}' expected '{expected_val}', got '{json_body.get(key)}'"
            except Exception as e:
                raise AssertionError(f"Failed to parse post data as JSON: {e}")

        # Assert response status code
        assert response.status == expected_status, f"Expected response status {expected_status}, got {response.status}"

        # Assert response JSON content
        if expected_response_json:
            json_data = response.json()
            for key, expected_val in expected_response_json.items():
                assert key in json_data and json_data[key] == expected_val, \
                    f"Response key '{key}' expected '{expected_val}', got '{json_data.get(key)}'"
