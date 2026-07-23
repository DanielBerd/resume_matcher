"""Read job emails from and send results through the Windows desktop Outlook.

This drives the *classic* Outlook desktop app (part of Microsoft 365 / Office)
through its COM automation interface, so it uses your already-signed-in
mailbox - no passwords, app registration, or IMAP/SMTP settings needed.

Requirements and limits:
  * Native Windows only (COM); it does not work under WSL, macOS, or Linux.
  * The classic Outlook desktop app must be installed and configured. The
    newer "Outlook for Windows" app does not expose COM automation.
  * Needs the pywin32 package (installed automatically on Windows via
    requirements.txt).

The rest of the pipeline talks to this through a small duck-typed interface
(fetch_unread_jobs / send_result / mark_read), so the orchestration in
email_watch.py can be tested with a fake mailbox instead of real Outlook.
"""

from __future__ import annotations

from dataclasses import dataclass

from .email_ingest import JobPosting

# olFolderInbox in the Outlook object model.
_OL_FOLDER_INBOX = 6
# olMailItem, for creating a new outgoing message.
_OL_MAIL_ITEM = 0


@dataclass
class InboxJob:
    """An unread job email: the posting plus what we need to reply and mark it."""

    posting: JobPosting
    sender_address: str
    entry_id: str  # Outlook's stable id for the message, used to re-fetch it


class OutlookMailbox:
    """Thin wrapper over the desktop Outlook COM object model."""

    def __init__(self) -> None:
        try:
            import pythoncom  # noqa: F401  (initializes COM for this thread)
            import win32com.client
        except ImportError as exc:  # pragma: no cover - Windows-only path
            raise RuntimeError(
                "Outlook watching needs the pywin32 package on Windows "
                "(pip install pywin32) and the classic Outlook desktop app."
            ) from exc

        self._app = win32com.client.Dispatch("Outlook.Application")
        self._ns = self._app.GetNamespace("MAPI")

    def own_address(self) -> str:  # pragma: no cover - Windows/COM-only
        """The SMTP address of the monitored mailbox (the signed-in account)."""
        try:
            return self._ns.Session.Accounts.Item(1).SmtpAddress
        except Exception:
            pass
        try:
            return self._ns.CurrentUser.AddressEntry.GetExchangeUser().PrimarySmtpAddress
        except Exception:
            return getattr(self._ns.CurrentUser, "Address", "") or ""

    def fetch_unread_jobs(self, subject_filter: str = "") -> list[InboxJob]:  # pragma: no cover
        """Return unread inbox emails (optionally filtered by subject text)."""
        inbox = self._ns.GetDefaultFolder(_OL_FOLDER_INBOX)
        needle = subject_filter.lower()
        jobs: list[InboxJob] = []
        for item in inbox.Items:
            # Skip non-mail items (meeting requests, etc.) and already-read mail.
            if getattr(item, "Class", None) != 43:  # 43 == olMail
                continue
            if not item.UnRead:
                continue
            subject = item.Subject or ""
            if needle and needle not in subject.lower():
                continue
            jobs.append(
                InboxJob(
                    posting=JobPosting(
                        source=subject or item.EntryID,
                        title=subject or "(no subject)",
                        body=item.Body or "",
                    ),
                    sender_address=_smtp_address(item),
                    entry_id=item.EntryID,
                )
            )
        return jobs

    def send_result(self, to_addr: str, subject: str, html_body: str) -> None:  # pragma: no cover
        """Send an HTML results email."""
        mail = self._app.CreateItem(_OL_MAIL_ITEM)
        mail.To = to_addr
        mail.Subject = subject
        mail.HTMLBody = html_body
        mail.Send()

    def mark_read(self, entry_id: str) -> None:  # pragma: no cover
        item = self._ns.GetItemFromID(entry_id)
        item.UnRead = False
        item.Save()


def _smtp_address(item) -> str:  # pragma: no cover - Windows/COM-only
    """Resolve a message's sender to an SMTP address.

    Exchange senders expose an X.500 DN in SenderEmailAddress rather than an
    SMTP address, so unwrap those via the Exchange user object.
    """
    try:
        if getattr(item, "SenderEmailType", "") == "EX":
            return item.Sender.GetExchangeUser().PrimarySmtpAddress
    except Exception:
        pass
    return getattr(item, "SenderEmailAddress", "") or ""
