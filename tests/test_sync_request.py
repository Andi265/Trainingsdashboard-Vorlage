import subprocess
import unittest
from datetime import date, datetime, timedelta

import briefing
import sync

REQUESTED = datetime(2026, 10, 25, 13, 55, tzinfo=briefing.TZ)


class FakeGit:
    """Stands in for subprocess.run: answers the git commands request_sync uses and records them."""

    def __init__(self, branch: str, push_ok: bool = True):
        self.branch, self.push_ok, self.calls = branch, push_ok, []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        out, code = "", 0
        if cmd[1:3] == ["branch", "--show-current"]:
            out = self.branch + "\n"
        elif cmd[1] == "commit-tree":
            out = "abc123\n"
        elif cmd[1] == "push":
            code = 0 if self.push_ok else 1
        return subprocess.CompletedProcess(cmd, code, out, "")


class RequestSyncTests(unittest.TestCase):
    def test_pushes_marked_commit_to_own_branch(self):
        git = FakeGit("claude/example-routine-branch")
        self.assertTrue(briefing.request_sync(run=git))
        commit = next(c for c in git.calls if c[1] == "commit-tree")
        message = commit[commit.index("-m") + 1]
        self.assertTrue(message.startswith(briefing.SYNC_MARKER))
        self.assertEqual(briefing.SYNC_MARKER, "[data-sync]")
        push = next(c for c in git.calls if c[1] == "push")
        self.assertIn("abc123:refs/heads/claude/example-routine-branch", push)
        self.assertNotIn("commit", [c[1] for c in git.calls])  # the local branch stays untouched

    def test_no_request_outside_claude_branch(self):
        git = FakeGit("main")
        self.assertFalse(briefing.request_sync(run=git))
        self.assertFalse(any(c[1] == "push" for c in git.calls))

    def test_failed_push_reports_false(self):
        self.assertFalse(briefing.request_sync(run=FakeGit("claude/x", push_ok=False)))


class WaitForRequestedSyncTests(unittest.TestCase):
    def run_wait(self, answers, timeout_min=8):
        answers, clock, sleeps = list(answers), [0.0], []

        def sleep(seconds):
            sleeps.append(seconds)
            clock[0] += seconds

        code = briefing.wait_for_requested_sync(REQUESTED, timeout_min, lambda: answers.pop(0) if answers else None,
                                                sleep=sleep, clock=lambda: clock[0])
        return code, sleeps

    def test_returns_when_the_requested_sync_arrives(self):
        old = REQUESTED - timedelta(hours=4)
        code, sleeps = self.run_wait([old, old, REQUESTED + timedelta(minutes=2)])
        self.assertEqual(code, 0)
        self.assertEqual(len(sleeps), 2)

    def test_gives_up_after_timeout(self):
        code, sleeps = self.run_wait([REQUESTED - timedelta(hours=4)] * 100, timeout_min=8)
        self.assertEqual(code, 1)
        self.assertLessEqual(sum(sleeps), 8 * 60)

    def test_missing_data_counts_as_not_arrived(self):
        code, _ = self.run_wait([None, None], timeout_min=1)
        self.assertEqual(code, 1)


class SyncDaysTests(unittest.TestCase):
    TODAY = date(2026, 10, 25)

    def test_number_is_taken_as_is(self):
        self.assertEqual(sync.days_to_sync("3", None, self.TODAY), 3)
        self.assertEqual(sync.days_to_sync("28", "2026-10-25T09:08:25+01:00", self.TODAY), 28)

    def test_auto_fetches_every_day_since_last_sync(self):
        self.assertEqual(sync.days_to_sync("auto", "2026-10-25T09:08:25+01:00", self.TODAY), 3)
        self.assertEqual(sync.days_to_sync("auto", "2026-10-15T20:15:00+02:00", self.TODAY), 11)

    def test_auto_is_capped_and_handles_missing_data(self):
        self.assertEqual(sync.days_to_sync("auto", "2026-08-01T07:00:00+02:00", self.TODAY), 30)
        self.assertEqual(sync.days_to_sync("auto", None, self.TODAY), 30)


if __name__ == "__main__":
    unittest.main()
