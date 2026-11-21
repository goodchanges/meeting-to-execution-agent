from html import escape
from time import sleep
from urllib.parse import urlsplit

import httpx


class GitHubError(Exception):
    pass


class GitHub:
    def __init__(
        self, token: str, repository: str, transport: httpx.BaseTransport | None = None
    ):
        self.token = token
        self.repository = repository
        self.transport = transport

    @property
    def configured(self):
        return bool(self.token and self.repository)

    def publish(self, item: dict, meeting: dict, base: str, reconcile: bool):
        if not self.configured:
            raise GitHubError("Configure the server GitHub repository and token first.")
        repo = self.repository
        marker = f"<!-- meetflow:action_item:{item['id']} -->"
        description = escape(item["description"]).replace("@", "＠")
        proof = escape(item["evidence_excerpt"]).replace("@", "＠")
        title = escape(meeting["title"]).replace("@", "＠")
        owner = escape(item["owner"]).replace("@", "＠")
        deadline = item["deadline"] or "Not specified"
        body = (
            f"{description}\n\nOwner: {owner}\n\nDeadline: {deadline}\n\n"
            f"Source: [{title}]({base.rstrip('/')}/meetings/{meeting['id']}) "
            f"({meeting['meeting_date']})\n\nEvidence ({item['evidence_ts'] or 'no timestamp'}): "
            f"{proof}\n\n{marker}"
        )
        with httpx.Client(
            base_url="https://api.github.com",
            timeout=httpx.Timeout(8),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            transport=self.transport,
        ) as client:
            endpoint = f"/repos/{repo}/issues"
            try:
                if reconcile:
                    for page in range(1, 11):
                        response = self.list_page(client, endpoint, page)
                        records = response.json()
                        for issue in records:
                            if "pull_request" not in issue and marker in (
                                issue.get("body") or ""
                            ):
                                return self.issue_result(issue, repo)
                        if "next" not in response.links:
                            break
                    else:
                        raise GitHubError(
                            "Unable to finish duplicate verification. Check the repository."
                        )
                response = client.post(
                    endpoint,
                    json={
                        "title": item["title"].replace("@", "＠"),
                        "body": body,
                        "labels": ["meetflow"],
                    },
                )
                check_response(response)
                return self.issue_result(response.json(), repo)
            except httpx.RequestError:
                raise GitHubError(
                    "GitHub did not respond. Retry will check for an existing issue."
                ) from None
            except (ValueError, TypeError, KeyError, AttributeError):
                raise GitHubError(
                    "GitHub returned an unexpected response. Retry will check for duplicates."
                ) from None

    @staticmethod
    def list_page(client: httpx.Client, endpoint: str, page: int):
        for attempt in range(3):
            try:
                response = client.get(
                    endpoint, params={"state": "all", "per_page": 100, "page": page}
                )
                if response.status_code < 500 or attempt == 2:
                    check_response(response)
                    return response
            except httpx.RequestError:
                if attempt == 2:
                    raise
            sleep(0.25 * 2**attempt)
        raise GitHubError("GitHub duplicate verification failed.")

    @staticmethod
    def issue_result(issue: dict, repo: str):
        number, url = issue["number"], issue["html_url"]
        parsed = urlsplit(url)
        if (
            not isinstance(number, int)
            or parsed.scheme != "https"
            or parsed.netloc != "github.com"
            or parsed.path.casefold() != f"/{repo}/issues/{number}".casefold()
        ):
            raise ValueError("Invalid issue response")
        return number, url


def check_response(response: httpx.Response):
    if response.is_success:
        return
    if response.status_code in {403, 429} and (
        response.status_code == 429
        or response.headers.get("x-ratelimit-remaining") == "0"
        or "retry-after" in response.headers
    ):
        raise GitHubError("GitHub rate limited this request. Retry later.")
    errors = {
        401: "GitHub rejected the configured token.",
        403: "The GitHub token lacks write access to Issues.",
        404: "The repository is unavailable to the configured token.",
        422: "GitHub rejected the issue. Check the repository and Issues configuration.",
    }
    raise GitHubError(
        errors.get(
            response.status_code, "GitHub could not complete the request. Try again."
        )
    )
