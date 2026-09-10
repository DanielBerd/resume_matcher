"""Tests for the inbox-watch orchestration, using a fake mailbox and LLM.

No Outlook, COM, or network involved: process_once talks to any object with
the fetch_unread_jobs / send_result / mark_read interface.
"""

from pathlib import Path

from resume_matcher.config import Config
from resume_matcher.documents import Resume
from resume_matcher.email_ingest import JobPosting
from resume_matcher.email_watch import process_once
from resume_matcher.outlook import InboxJob


class FakeLLM:
    """Returns a fixed score so match_job runs without a real model."""

    def complete(self, system_prompt, user_prompt):
        return '{"score": 77, "comment": "Solid overlap."}'


class FakeMailbox:
    def __init__(self, jobs, own="watched@myinbox.com"):
        self._jobs = jobs
        self._own = own
        self.sent = []          # (to_addr, subject, html_body)
        self.marked_read = []   # entry_ids

    def own_address(self):
        return self._own

    def fetch_unread_jobs(self, subject_filter=""):
        return self._jobs

    def send_result(self, to_addr, subject, html_body):
        self.sent.append((to_addr, subject, html_body))

    def mark_read(self, entry_id):
        self.marked_read.append(entry_id)


def _job(entry_id="id1", sender="hr@example.com", title="Python Dev"):
    return InboxJob(
        posting=JobPosting(source=title, title=title, body="We need Python."),
        sender_address=sender,
        entry_id=entry_id,
    )


def _resumes():
    return [Resume(path=Path("a.pdf"), text="Python engineer"),
            Resume(path=Path("b.pdf"), text="Marketing manager")]


def test_sends_to_monitored_inbox_and_marks_read():
    mailbox = FakeMailbox([_job(sender="hr@acme.com")], own="watched@myinbox.com")
    handled = process_once(Config(), mailbox, FakeLLM(), _resumes())

    assert handled == 1
    assert len(mailbox.sent) == 1
    to_addr, subject, html = mailbox.sent[0]
    assert to_addr == "watched@myinbox.com"   # back to the monitored mailbox, not the sender
    assert "Python Dev" in subject
    assert "77" in html and "a.pdf" in html   # results made it into the email
    assert mailbox.marked_read == ["id1"]


def test_fixed_recipient_overrides_default():
    config = Config()
    config.result_recipient = "elsewhere@example.com"
    mailbox = FakeMailbox([_job(sender="hr@acme.com")], own="watched@myinbox.com")
    process_once(config, mailbox, FakeLLM(), _resumes())
    assert mailbox.sent[0][0] == "elsewhere@example.com"


def test_skips_send_when_no_recipient():
    mailbox = FakeMailbox([_job(sender="hr@acme.com")], own="")
    process_once(Config(), mailbox, FakeLLM(), _resumes())
    assert mailbox.sent == []
    assert mailbox.marked_read == []


def test_no_unread_emails_is_a_noop():
    mailbox = FakeMailbox([])
    assert process_once(Config(), mailbox, FakeLLM(), _resumes()) == 0
    assert mailbox.sent == []
