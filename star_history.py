#!/usr/bin/env python3
"""Export GitHub's weekly star-history buckets as cumulative CSV (stdlib only)."""

import argparse
import csv
from datetime import datetime, timezone
import http.client
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

__version__ = "0.1.0"
API_ROOT = "https://api.github.com"
API_VERSION = "2026-03-10"
PER_PAGE = 30
MAX_BODY = 1024 * 1024
WEEK_SECONDS = 7 * 24 * 60 * 60
CSV_COLUMNS = ("week_start", "stars_cumulative", "stars_added")


class ExportError(Exception):
    """A safe, user-facing error; never includes response bodies or credentials."""


def repository_name(value):
    owner, separator, repo = value.partition("/")
    if (not separator or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", owner)
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", repo)
            or repo in (".", "..") or repo.endswith(".git")):
        raise argparse.ArgumentTypeError("use owner/repo, without a URL or .git suffix")
    return value


def positive_timeout(value):
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("timeout must be a number from 0 (exclusive) to 120 seconds")
    if not math.isfinite(number) or not 0 < number <= 120:
        raise argparse.ArgumentTypeError("timeout must be greater than 0 and at most 120 seconds")
    return number


def page_limit(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("max-pages must be an integer from 1 to 100")
    if not 1 <= number <= 100:
        raise argparse.ArgumentTypeError("max-pages must be an integer from 1 to 100")
    return number


class NoRedirects(HTTPRedirectHandler):
    # urllib otherwise forwards Authorization to redirect destinations.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_error(status, headers):
    if status == 429 or (status == 403 and (
            headers.get("X-RateLimit-Remaining") == "0" or headers.get("Retry-After"))):
        message = "GitHub rate limit reached. Wait before retrying; GITHUB_TOKEN may increase your quota."
        retry = headers.get("Retry-After", "")
        reset = headers.get("X-RateLimit-Reset", "")
        if re.fullmatch(r"[0-9]{1,10}", retry):
            message += " Retry after {} seconds.".format(retry)
        elif re.fullmatch(r"[0-9]{1,12}", reset):
            message += " Rate-limit reset (Unix seconds): {}.".format(reset)
    elif status == 401:
        message = "Authentication failed. Check GITHUB_TOKEN or unset it for public repositories."
    elif status == 403:
        message = "GitHub denied access (or applied a secondary rate limit). Check repository access and Metadata: read; retry later if limited."
    elif status == 404:
        message = "Repository not found or not accessible. Check owner/repo and token access for private repositories."
    elif status in (301, 302, 303, 307, 308):
        message = "GitHub redirected this request. Retry using the repository's current owner/repo."
    elif status == 422:
        message = "GitHub rejected the history request. Check API availability and pagination limits."
    elif status >= 500:
        message = "GitHub is temporarily unavailable. Retry later."
    else:
        message = "GitHub returned an unexpected response."
    return ExportError("HTTP {}: {}".format(status, message))


class GitHubClient:
    def __init__(self, token=None, timeout=20):
        self.timeout = timeout
        self.headers = {"Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": API_VERSION,
                        "User-Agent": "github-star-history-csv/" + __version__}
        if token:
            if any(ord(char) < 33 or ord(char) > 126 for char in token):
                raise ExportError("GITHUB_TOKEN contains invalid characters. Check the environment value.")
            self.headers["Authorization"] = "Bearer " + token
        self.opener = build_opener(NoRedirects())

    def get(self, url):
        # Both initial URLs and pagination URLs must stay on this origin.
        if urlsplit(url).scheme != "https" or urlsplit(url).netloc != "api.github.com":
            raise ExportError("Refusing an API URL outside https://api.github.com.")
        request = Request(url, headers=self.headers)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise http_error(response.status, response.headers)
                body = response.read(MAX_BODY + 1)
                if len(body) > MAX_BODY:
                    raise ExportError("GitHub response exceeds the 1 MiB safety limit.")
                headers = response.headers
        except HTTPError as error:
            error.close()
            raise http_error(error.code, error.headers) from None
        except (URLError, OSError, http.client.HTTPException):
            raise ExportError("Network request failed or timed out. Check your connection, TLS certificates, and proxy; retry later.") from None
        try:
            return json.loads(body), headers
        except (ValueError, UnicodeError, RecursionError):
            raise ExportError("GitHub returned invalid JSON; no CSV was written.") from None


def pagination_links(header):
    """Parse GitHub's Link header; fail closed if a link cannot be understood."""
    links = {}
    if not header:
        return links
    for item in re.split(r",\s*(?=<)", header):
        match = re.fullmatch(r'\s*<([^<>]+)>\s*;\s*rel="([a-z ]+)"\s*', item)
        if not match:
            raise ExportError("Malformed GitHub pagination header; refusing an incomplete export.")
        for relation in match[2].split():
            if relation in links:
                raise ExportError("Duplicate pagination relation in GitHub response.")
            links[relation] = match[1]
    return links


def validate_page_url(url, repository, expected_page=None):
    parsed = urlsplit(url)
    named_path = "/repos/" + repository + "/stargazers/history"
    if (parsed.scheme != "https" or parsed.netloc != "api.github.com" or parsed.fragment
            or not (parsed.path.lower() == named_path.lower()
                    or re.fullmatch(r"/repositories/[0-9]+/stargazers/history", parsed.path))):
        raise ExportError("Unsafe or unexpected pagination URL; export stopped.")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if (set(query) != {"page", "per_page"} or query["per_page"] != [str(PER_PAGE)]
            or len(query["page"]) != 1 or not re.fullmatch(r"[0-9]+", query["page"][0])):
        raise ExportError("Unexpected pagination parameters; export stopped.")
    page = int(query["page"][0])
    if not 1 <= page <= 100:
        raise ExportError("History exceeds GitHub's 100-page limit; refusing a truncated export.")
    if expected_page is not None and page != expected_page:
        raise ExportError("Pagination repeated or skipped a page; refusing an incomplete export.")
    return page


def validate_bucket(bucket):
    if not isinstance(bucket, dict) or not {"week", "total", "days"} <= bucket.keys():
        raise ExportError("Unexpected history schema: each week needs week, total, and days.")
    week, total, days = bucket["week"], bucket["total"], bucket["days"]
    if type(week) is not int or week < 0 or type(total) is not int or total < 0:
        raise ExportError("Invalid history timestamp or weekly count.")
    if (not isinstance(days, list) or len(days) != 7
            or any(type(day) is not int or day < 0 for day in days) or sum(days) != total):
        raise ExportError("Invalid daily counts or weekly total; export stopped.")
    try:
        datetime.fromtimestamp(week, timezone.utc)
    except (ValueError, OverflowError, OSError):
        raise ExportError("History timestamp is outside the supported date range.") from None
    return week, total


def fetch_history(repository, client, max_pages=100):
    url = API_ROOT + "/repos/" + repository + "/stargazers/history?per_page=30&page=1"
    buckets = {}
    previous_oldest = None
    pagination_path = None
    for page in range(1, max_pages + 1):
        data, headers = client.get(url)
        if not isinstance(data, list) or len(data) > PER_PAGE:
            raise ExportError("Unexpected history response: expected an array of at most 30 weeks.")
        links = pagination_links(headers.get("Link"))
        current = [validate_bucket(bucket) for bucket in data]
        if current and previous_oldest is not None and max(week for week, _ in current) >= previous_oldest:
            raise ExportError("History pages overlap or changed while fetching. Retry the export.")
        for week, total in current:
            if week in buckets:
                raise ExportError("Duplicate week in history; export stopped.")
            buckets[week] = total
        if current:
            previous_oldest = min(week for week, _ in current)
        last_page = validate_page_url(links["last"], repository) if "last" in links else page
        if last_page < page:
            raise ExportError("Invalid last-page link; export stopped.")
        if "next" not in links:
            if last_page > page:
                raise ExportError("Missing next-page link; refusing a truncated export.")
            return cumulative_rows(buckets), page
        if not current:
            raise ExportError("Empty page before the end of history; export stopped.")
        next_url = links["next"]
        validate_page_url(next_url, repository, page + 1)
        next_path = urlsplit(next_url).path.lower()
        if pagination_path is not None and next_path != pagination_path:
            raise ExportError("Pagination changed repositories; export stopped.")
        pagination_path = next_path
        if page >= max_pages:
            raise ExportError("History needs more than --max-pages {}. Increase the limit (up to 100); no CSV was written.".format(max_pages))
        url = next_url
    raise ExportError("History page limit reached.")


def cumulative_rows(buckets):
    total = 0
    previous = None
    rows = []
    for week, count in sorted(buckets.items()):
        # Allow timezone/DST shifts, but never silently invent a missing week.
        if previous is not None and not WEEK_SECONDS - 86400 <= week - previous <= WEEK_SECONDS + 86400:
            raise ExportError("History has missing or irregular weeks. Refusing an incomplete cumulative series.")
        total += count
        week_start = datetime.fromtimestamp(week, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append((week_start, total, count))
        previous = week
    return rows


def check_destination(path, force):
    if os.path.lexists(path):
        if path.is_dir():
            raise ExportError("Output is a directory. Choose a CSV file path.")
        if not force:
            raise ExportError("Output already exists. Choose another path or pass --force to replace it.")
    if not path.parent.is_dir():
        raise ExportError("Output directory does not exist. Create it before exporting.")


def write_csv(stream, rows):
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    writer.writerows(rows)


def save_csv(path, rows, force=False):
    """Publish only a complete file. A hard link provides atomic no-clobber mode."""
    check_destination(path, force)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                                         prefix="." + path.name + ".", suffix=".tmp", delete=False) as stream:
            temp_path = Path(stream.name)
            write_csv(stream, rows)
            stream.flush()
            os.fsync(stream.fileno())
        if force:
            os.replace(temp_path, path)
        else:
            try:
                os.link(temp_path, path)
            except FileExistsError:
                raise ExportError("Output appeared during export. Choose another path or use --force.") from None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def parser():
    result = argparse.ArgumentParser(description="Export GitHub weekly star history as CSV: week_start, stars_cumulative, stars_added. Public repositories need no token.")
    result.add_argument("repository", type=repository_name, metavar="owner/repo")
    result.add_argument("--output", required=True, metavar="PATH", help="CSV destination; use - explicitly for stdout")
    result.add_argument("--force", action="store_true", help="atomically replace an existing output file")
    result.add_argument("--timeout", type=positive_timeout, default=20, metavar="SECONDS", help="socket timeout per request (default: 20; maximum: 120)")
    result.add_argument("--max-pages", type=page_limit, default=100, metavar="N", help="maximum history pages (1–100; default: 100; 30 weeks per page)")
    result.add_argument("--version", action="version", version=__version__)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if args.force and args.output == "-":
        parser().error("--force is only valid for an output file")
    if not args.output:
        parser().error("--output must be a file path or -")
    try:
        path = None if args.output == "-" else Path(args.output)
        if path is not None:
            check_destination(path, args.force)
        client = GitHubClient(token=os.environ.get("GITHUB_TOKEN"), timeout=args.timeout)
        rows, pages = fetch_history(args.repository, client, args.max_pages)
        if path is None:
            write_csv(sys.stdout, rows)
            sys.stdout.flush()
        else:
            save_csv(path, rows, args.force)
        destination = "stdout" if path is None else "output file"
        print("Exported {} weeks from {} pages to {}.".format(len(rows), pages, destination), file=sys.stderr)
        if not rows:
            print("GitHub returned no history: CSV contains only the header (not a zero-star estimate).", file=sys.stderr)
        return 0
    except ExportError as error:
        print("error: " + str(error), file=sys.stderr)
        return 1
    except BrokenPipeError:
        # Avoid a second BrokenPipeError when Python flushes stdout on shutdown.
        sys.stdout = open(os.devnull, "w")
        return 1
    except OSError:
        print("error: Cannot write output. Check permissions, free space, and filesystem support for atomic files.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("error: Export interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
