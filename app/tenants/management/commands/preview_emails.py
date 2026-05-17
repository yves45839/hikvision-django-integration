"""
Render every transactional email template with sample data and write the
HTML output to disk for visual review (or send a real email if --to is given).

Usage:
    python manage.py preview_emails                    # write HTML files to ./email_previews/
    python manage.py preview_emails --out path/to/dir
    python manage.py preview_emails --to me@example.com  # send all variants by email
    python manage.py preview_emails --only password_reset --lang fr
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone as dt_tz
from pathlib import Path

from django.core.management.base import BaseCommand

from tenants.emails import (
    SUPPORTED_LANGS,
    render_branded_email,
    send_branded_email,
)


def _sample_contexts():
    """Sample context payloads keyed by template name."""
    now = datetime.now(tz=dt_tz.utc)
    return {
        "password_reset": {
            "first_name": "Marie",
            "user_email": "marie.dupont@example.com",
            "otp_code": "428193",
            "reset_link": "https://app.label-retail.com/auth/reset-password?token=8f3b2a1e-94d6-4e2a-9c01-1d8b6f7a52e0",
            "expires_at": now + timedelta(minutes=30),
        },
        "payment_success": {
            "first_name": "Marie",
            "tenant_name": "Boutique du Centre",
            "plan_name": "Pro Mensuel",
            "amount": "49.00",
            "currency": "EUR",
            "invoice_number": "INV-2026-00482",
            "invoice_url": "https://invoice.stripe.com/i/acct_xxx/test_yyy",
            "invoice_pdf": "https://invoice.stripe.com/i/acct_xxx/test_yyy/pdf",
            "paid_at": now,
            "period_start": now,
            "period_end": now + timedelta(days=30),
        },
        "payment_failed": {
            "first_name": "Marie",
            "tenant_name": "Boutique du Centre",
            "amount": "49.00",
            "currency": "EUR",
            "invoice_number": "INV-2026-00483",
            "failure_reason": "Carte refusée par la banque (insufficient_funds).",
            "retry_url": "https://app.label-retail.com/billing",
            "attempted_at": now,
        },
    }


class Command(BaseCommand):
    help = "Render or send all branded transactional email templates with sample data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--out",
            default="email_previews",
            help="Output directory for the rendered HTML files. Default: ./email_previews",
        )
        parser.add_argument(
            "--to",
            default="",
            help="If set, send each template to this email address instead of writing files.",
        )
        parser.add_argument(
            "--lang",
            default="",
            help="Restrict to one language code (fr or en). Default: all supported.",
        )
        parser.add_argument(
            "--only",
            default="",
            help="Restrict to a single template name (password_reset, payment_success, payment_failed).",
        )

    def handle(self, *args, **options):
        out_dir = Path(options["out"]).resolve()
        recipient = str(options["to"] or "").strip()
        lang_filter = str(options["lang"] or "").strip().lower()
        only = str(options["only"] or "").strip()

        contexts = _sample_contexts()
        if only:
            if only not in contexts:
                self.stderr.write(self.style.ERROR(
                    f"Unknown template '{only}'. Valid: {', '.join(contexts)}"
                ))
                return
            contexts = {only: contexts[only]}

        languages = [lang_filter] if lang_filter in SUPPORTED_LANGS else list(SUPPORTED_LANGS)

        if recipient:
            for name, ctx in contexts.items():
                for lang in languages:
                    self.stdout.write(f"  Sending {name} [{lang}] to {recipient} ...")
                    send_branded_email(
                        to_email=recipient,
                        template_name=name,
                        context=ctx,
                        lang=lang,
                    )
            self.stdout.write(self.style.SUCCESS("All sample emails sent."))
            return

        out_dir.mkdir(parents=True, exist_ok=True)
        index_lines = [
            "<!DOCTYPE html><html><head><meta charset='utf-8'>",
            "<title>Label Retail — email previews</title>",
            "<style>body{font-family:system-ui,-apple-system,sans-serif;background:#F4F6FA;margin:0;padding:24px;}",
            "h1{color:#243C8C;margin:0 0 16px;}",
            "ul{list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;}",
            "li{background:#fff;border:1px solid #E5E8F0;border-radius:8px;padding:14px 18px;}",
            "a{color:#E86B30;font-weight:600;text-decoration:none;}",
            "a:hover{text-decoration:underline;}",
            ".tag{font-size:11px;color:#6B7488;text-transform:uppercase;letter-spacing:0.6px;}</style></head><body>",
            "<h1>Label Retail — aperçu des emails</h1><ul>",
        ]

        for name, ctx in contexts.items():
            for lang in languages:
                subject, html_body, text_body = render_branded_email(
                    template_name=name,
                    context=ctx,
                    lang=lang,
                )
                html_path = out_dir / f"{name}.{lang}.html"
                text_path = out_dir / f"{name}.{lang}.txt"
                html_path.write_text(html_body, encoding="utf-8")
                text_path.write_text(text_body, encoding="utf-8")
                index_lines.append(
                    f"<li><div class='tag'>{lang.upper()} · {name}</div>"
                    f"<div style='margin:6px 0;color:#1A2238;'>{subject}</div>"
                    f"<a href='{html_path.name}'>HTML</a> &middot; "
                    f"<a href='{text_path.name}'>Texte</a></li>"
                )
                self.stdout.write(f"  wrote {html_path.relative_to(out_dir.parent)}")

        index_lines.append("</ul></body></html>")
        (out_dir / "index.html").write_text("\n".join(index_lines), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(
            f"All previews written to {out_dir}{os.sep}index.html"
        ))
