"""Offline contract and CLI tests. All inline API responses are synthetic."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
from email.message import Message
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import star_history as sh

REPO = "octocat/example"
BASE = "https://api.github.com/repositories/123/stargazers/history?per_page=30&page="
WEEK = 1677369600


def bucket(index, total=1):
    return {"week": WEEK + index * sh.WEEK_SECONDS, "total": total,
            "days": [total, 0, 0, 0, 0, 0, 0]}


def header(**values):
    result = Message()
    for key, value in values.items():
        result[key.replace("_", "-")] = value
    return result


def client(*pages):
    result = Mock()
    result.get.side_effect = pages
    return result


class HistoryTests(unittest.TestCase):
    def test_paginates_numeric_repository_links_and_accumulates_oldest_first(self):
        api = client(([bucket(2, 7), bucket(1, 0)], header(Link='<{}2>; rel="next", <{}2>; rel="last"'.format(BASE, BASE))),
                     ([bucket(0, 3)], header(Link='<{}1>; rel="prev"'.format(BASE))))
        rows, pages = sh.fetch_history(REPO, api)
        self.assertEqual(pages, 2)
        self.assertEqual(rows, [("2023-02-26T00:00:00Z", 3, 3), ("2023-03-05T00:00:00Z", 3, 0), ("2023-03-12T00:00:00Z", 10, 7)])
        self.assertEqual(api.get.call_args_list[1].args, (BASE + '2',))

    def test_sorts_within_a_page(self):
        rows, _ = sh.fetch_history(REPO, client(([bucket(0, 3), bucket(1, 2)], {})))
        self.assertEqual([row[1] for row in rows], [3, 5])
        self.assertEqual([row[2] for row in rows], [3, 2])

    def test_empty_is_not_fabricated_zero(self):
        self.assertEqual(sh.fetch_history(REPO, client(([], {}))), ([], 1))

    def test_explicit_zero_week_is_preserved(self):
        rows, _ = sh.fetch_history(REPO, client(([bucket(0, 0)], {})))
        self.assertEqual(rows, [("2023-02-26T00:00:00Z", 0, 0)])

    def test_page_limit_fails_instead_of_returning_partial_history(self):
        api = client(([bucket(0)], header(Link='<{}2>; rel="next"'.format(BASE))))
        with self.assertRaisesRegex(sh.ExportError, 'max-pages'):
            sh.fetch_history(REPO, api, max_pages=1)
        self.assertEqual(api.get.call_count, 1)

    def test_missing_next_link_with_later_last_page(self):
        with self.assertRaisesRegex(sh.ExportError, 'Missing next'):
            sh.fetch_history(REPO, client(([bucket(0)], header(Link='<{}2>; rel="last"'.format(BASE)))))

    def test_empty_intermediate_page(self):
        with self.assertRaisesRegex(sh.ExportError, 'Empty page'):
            sh.fetch_history(REPO, client(([], header(Link='<{}2>; rel="next"'.format(BASE)))))

    def test_duplicate_week(self):
        with self.assertRaisesRegex(sh.ExportError, 'Duplicate week'):
            sh.fetch_history(REPO, client(([bucket(0), bucket(0)], {})))

    def test_overlapping_or_changing_pages(self):
        api = client(([bucket(0)], header(Link='<{}2>; rel="next"'.format(BASE))), ([bucket(0)], {}))
        with self.assertRaisesRegex(sh.ExportError, 'overlap'):
            sh.fetch_history(REPO, api)

    def test_gap_is_not_filled(self):
        with self.assertRaisesRegex(sh.ExportError, 'missing or irregular'):
            sh.fetch_history(REPO, client(([bucket(2), bucket(0)], {})))

    def test_non_utc_week_and_dst_shift_are_not_relabelled_midnight(self):
        rows = sh.cumulative_rows({WEEK + 3600: 3, WEEK + sh.WEEK_SECONDS: 2})
        self.assertEqual(rows[0][0], '2023-02-26T01:00:00Z')
        self.assertEqual(rows[1][1], 5)

    def test_missing_response_is_an_error(self):
        for data in (None, {}, '', {'message': 'error'}, [bucket(0)] * 31):
            with self.subTest(data=type(data).__name__), self.assertRaises(sh.ExportError):
                sh.fetch_history(REPO, client((data, {})))

    def test_bad_bucket_values(self):
        bad = [None, {}, {**bucket(0), 'week': True}, {**bucket(0), 'week': -1},
               {**bucket(0), 'week': 10**100}, {**bucket(0), 'total': -1},
               {**bucket(0), 'total': True}, {**bucket(0), 'total': '1'},
               {**bucket(0), 'days': [1]}, {**bucket(0), 'days': [True] + [0]*6},
               {**bucket(0), 'days': [0]*7}, {**bucket(0), 'days': [-1, 2, 0, 0, 0, 0, 0]}]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(sh.ExportError):
                sh.validate_bucket(value)

    def test_pagination_keeps_same_repository_path(self):
        api = client(([bucket(2)], header(Link='<{}2>; rel="next"'.format(BASE))),
                     ([bucket(1)], header(Link='<{}3>; rel="next"'.format(BASE.replace('/123/', '/456/')))))
        with self.assertRaisesRegex(sh.ExportError, 'changed repositories'):
            sh.fetch_history(REPO, api)

    def test_rejects_unsafe_or_wrong_pagination(self):
        urls = [BASE.replace('https:', 'http:')+'2', BASE.replace('api.github.com', 'evil.example')+'2',
                BASE.replace('api.github.com', 'api.github.com@evil.example')+'2',
                BASE+'2#fragment', BASE+'2&page=2', BASE.replace('per_page=30', 'per_page=100')+'2',
                BASE+'1', BASE+'3', BASE+'101', BASE.replace('/stargazers/history', '/issues')+'2',
                BASE+'2&token=hidden', BASE.replace('api.github.com', 'api.github.com:443')+'2']
        for url in urls:
            with self.subTest(url=url), self.assertRaises(sh.ExportError):
                sh.validate_page_url(url, REPO, 2)

    def test_malformed_links_fail_closed(self):
        for value in ('broken', '<url>; rel=next', '<url>; rel="next", <other>; rel="next"'):
            with self.subTest(value=value), self.assertRaises(sh.ExportError):
                sh.pagination_links(value)

    def test_full_last_page_is_allowed(self):
        rows, pages = sh.fetch_history(REPO, client(([bucket(i) for i in range(30)], {})))
        self.assertEqual((len(rows), pages), (30, 1))


class NetworkTests(unittest.TestCase):
    def make_client(self, body=b'[]', status=200, headers=None):
        api = sh.GitHubClient(token='test-placeholder', timeout=7)
        response = Mock(status=status, headers=headers or header())
        response.read.return_value = body
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        api.opener = Mock()
        api.opener.open.return_value = response
        return api

    def test_request_headers_timeout_and_json(self):
        api = self.make_client(json.dumps([bucket(0)]).encode())
        self.assertEqual(api.get(BASE+'1')[0], [bucket(0)])
        request = api.opener.open.call_args.args[0]
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-placeholder')
        self.assertEqual(request.get_header('X-github-api-version'), '2026-03-10')
        self.assertEqual(api.opener.open.call_args.kwargs['timeout'], 7)

    def test_no_token_has_no_authorization_header(self):
        self.assertNotIn('Authorization', sh.GitHubClient().headers)

    def test_invalid_token_fails_without_disclosing_it(self):
        for token in ('secret\nvalue', 'secret value', 'secret\u2603'):
            with self.assertRaises(sh.ExportError) as error:
                sh.GitHubClient(token)
            self.assertNotIn('secret', str(error.exception))

    def test_http_statuses_are_actionable_and_hide_response_body(self):
        expected = {401: 'Authentication', 403: 'denied access', 404: 'not found',
                    429: 'rate limit', 422: 'rejected', 500: 'temporarily', 301: 'redirected'}
        for status, message in expected.items():
            with self.subTest(status=status):
                api = self.make_client()
                api.opener.open.side_effect = HTTPError(BASE+'1', status, 'secret', header(), io.BytesIO(b'secret'))
                with self.assertRaisesRegex(sh.ExportError, message) as error:
                    api.get(BASE+'1')
                self.assertNotIn('secret', str(error.exception))

    def test_primary_and_secondary_rate_limit_headers(self):
        for status, headers in ((403, header(X_RateLimit_Remaining='0', X_RateLimit_Reset='1790535951')),
                                (403, header(Retry_After='60')), (429, header(Retry_After='60'))):
            self.assertIn('rate limit', str(sh.http_error(status, headers)))
        self.assertIn('60 seconds', str(sh.http_error(429, header(Retry_After='60'))))
        self.assertNotIn('secret', str(sh.http_error(429, header(Retry_After='secret'))))

    def test_network_errors_do_not_leak_details(self):
        for error in (URLError('secret'), TimeoutError('secret'), ConnectionResetError('secret'), sh.http.client.IncompleteRead(b'secret')):
            api = self.make_client()
            api.opener.open.side_effect = error
            with self.assertRaisesRegex(sh.ExportError, 'Network request') as caught:
                api.get(BASE+'1')
            self.assertNotIn('secret', str(caught.exception))

    def test_malformed_json_and_excessive_response(self):
        for data in (b'', b'{', b'\xff', b' ' * (sh.MAX_BODY + 1)):
            with self.subTest(data=data[:10]), self.assertRaises(sh.ExportError):
                self.make_client(data).get(BASE+'1')

    def test_redirects_are_not_followed_with_credentials(self):
        self.assertIsNone(sh.NoRedirects().redirect_request(None, None, 302, '', {}, 'https://evil.example'))

    def test_get_rejects_foreign_origin_before_request(self):
        api = self.make_client()
        with self.assertRaises(sh.ExportError):
            api.get('https://evil.example')
        api.opener.open.assert_not_called()

    def test_unexpected_success_status_is_error(self):
        with self.assertRaisesRegex(sh.ExportError, 'HTTP 204'):
            self.make_client(status=204).get(BASE+'1')


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'stars.csv'
        self.rows = [('2023-02-26T00:00:00Z', 5, 5)]

    def test_csv_bytes_and_newlines(self):
        sh.save_csv(self.path, self.rows)
        self.assertEqual(self.path.read_bytes(), b'week_start,stars_cumulative,stars_added\n2023-02-26T00:00:00Z,5,5\n')
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_empty_output_has_header_only(self):
        sh.save_csv(self.path, [])
        self.assertEqual(self.path.read_text(), 'week_start,stars_cumulative,stars_added\n')

    def test_existing_file_is_preserved(self):
        self.path.write_text('original')
        with self.assertRaisesRegex(sh.ExportError, 'already exists'):
            sh.save_csv(self.path, self.rows)
        self.assertEqual(self.path.read_text(), 'original')

    def test_force_replaces_complete_file(self):
        self.path.write_text('original')
        sh.save_csv(self.path, self.rows, force=True)
        self.assertTrue(self.path.read_text().startswith('week_start,stars_cumulative,stars_added\n'))

    def test_write_failure_keeps_old_file_and_cleans_temporary(self):
        self.path.write_text('original')
        with patch.object(sh, 'write_csv', side_effect=OSError('disk full')), self.assertRaises(OSError):
            sh.save_csv(self.path, self.rows, force=True)
        self.assertEqual(self.path.read_text(), 'original')
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_write_failure_does_not_create_new_file(self):
        with patch.object(sh, 'write_csv', side_effect=OSError('disk full')), self.assertRaises(OSError):
            sh.save_csv(self.path, self.rows)
        self.assertEqual(list(self.path.parent.iterdir()), [])

    def test_file_appearing_during_export_is_not_overwritten(self):
        def race(source, target):
            Path(target).write_text('another writer')
            raise FileExistsError()
        with patch.object(sh.os, 'link', side_effect=race), self.assertRaisesRegex(sh.ExportError, 'appeared'):
            sh.save_csv(self.path, self.rows)
        self.assertEqual(self.path.read_text(), 'another writer')
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    @unittest.skipUnless(hasattr(os, 'symlink') and os.name != 'nt', 'POSIX symlinks')
    def test_force_replaces_symlink_without_touching_target(self):
        target = self.path.parent / 'target.csv'
        target.write_text('original')
        self.path.symlink_to(target)
        with self.assertRaises(sh.ExportError):
            sh.save_csv(self.path, self.rows)
        sh.save_csv(self.path, self.rows, force=True)
        self.assertFalse(self.path.is_symlink())
        self.assertEqual(target.read_text(), 'original')

    def test_missing_parent_and_directory_target(self):
        for path in (self.path / 'missing.csv', self.path.parent):
            with self.assertRaises(sh.ExportError):
                sh.save_csv(path, self.rows)

    def test_csv_uses_standard_escaping(self):
        stream = io.StringIO()
        sh.write_csv(stream, [('a,"b', 1, 1)])
        self.assertEqual(stream.getvalue(), 'week_start,stars_cumulative,stars_added\n"a,""b",1,1\n')


class CLITests(unittest.TestCase):
    def invoke(self, arguments, response=([('2023-02-26T00:00:00Z', 5, 5)], 1), error=None):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(out), redirect_stderr(err), patch.object(sh, 'fetch_history', return_value=response, side_effect=error) as fetch:
            status = sh.main(arguments)
        return status, out.getvalue(), err.getvalue(), fetch

    def test_stdout_is_explicit_and_diagnostics_go_to_stderr(self):
        status, out, err, _ = self.invoke([REPO, '--output', '-'])
        self.assertEqual(status, 0)
        self.assertEqual(out, 'week_start,stars_cumulative,stars_added\n2023-02-26T00:00:00Z,5,5\n')
        self.assertIn('Exported 1 weeks', err)

    def test_empty_history_explained(self):
        status, out, err, _ = self.invoke([REPO, '--output', '-'], response=([], 1))
        self.assertEqual((status, out), (0, 'week_start,stars_cumulative,stars_added\n'))
        self.assertIn('no history', err)

    def test_failure_leaves_stdout_empty(self):
        status, out, err, _ = self.invoke([REPO, '--output', '-'], error=sh.ExportError('HTTP 404: not found'))
        self.assertEqual((status, out), (1, ''))
        self.assertIn('404', err)

    def test_failure_preserves_file_even_with_force(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stars.csv'
            path.write_text('original')
            status, out, _, _ = self.invoke([REPO, '--output', str(path), '--force'], error=sh.ExportError('offline'))
            self.assertEqual((status, out, path.read_text()), (1, '', 'original'))

    def test_file_export_has_no_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stars.csv'
            status, out, _, _ = self.invoke([REPO, '--output', str(path)])
            self.assertEqual((status, out), (0, ''))
            self.assertTrue(path.exists())

    def test_existing_file_fails_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stars.csv'
            path.write_text('original')
            status, _, _, fetch = self.invoke([REPO, '--output', str(path)])
            self.assertEqual(status, 1)
            fetch.assert_not_called()

    def test_environment_token_is_used(self):
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'test-placeholder'}), patch.object(sh, 'GitHubClient') as factory, patch.object(sh, 'fetch_history', return_value=([], 1)), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(sh.main([REPO, '--output', '-']), 0)
        factory.assert_called_once_with(token='test-placeholder', timeout=20)

    def test_keyboard_interrupt(self):
        status, out, err, _ = self.invoke([REPO, '--output', '-'], error=KeyboardInterrupt())
        self.assertEqual((status, out), (130, ''))
        self.assertIn('interrupted', err)

    def test_file_error_has_no_traceback(self):
        with patch.object(sh, 'save_csv', side_effect=PermissionError('secret')):
            status, out, err, _ = self.invoke([REPO, '--output', 'nonexistent-export-test.csv'])
        self.assertEqual((status, out), (1, ''))
        self.assertIn('Cannot write', err)
        self.assertNotIn('secret', err)

    def test_invalid_repository_names(self):
        for value in ('repo', '/repo', 'owner/', 'owner/repo/extra', 'https://github.com/owner/repo', 'owner/..', 'owner/.', 'owner/repo.git', '-owner/repo', 'owner/repo?x=1', 'owner/repo\n', 'a'*40+'/repo'):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                sh.repository_name(value)

    def test_valid_repository_names(self):
        for value in ('vitalio-sh/chatgpt-3.5-turbo', 'a/.github', 'Owner/Repo_Name', 'a/b'):
            self.assertEqual(sh.repository_name(value), value)

    def test_invalid_timeouts_and_page_limits(self):
        for value in ('nan', 'inf', '0', '-1', '121', 'text'):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                sh.positive_timeout(value)
        for value in ('0', '-1', '101', '1.5', 'text'):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                sh.page_limit(value)

    def test_cli_help_version_and_usage_exit_codes_in_subprocess(self):
        for args, status in ((['--help'], 0), (['--version'], 0), ([REPO], 2),
                             ([REPO, '--output', '-', '--force'], 2),
                             ([REPO, '--output', ''], 2)):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, str(Path(sh.__file__).resolve())] + args, capture_output=True, text=True)
                self.assertEqual(result.returncode, status)
                self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
