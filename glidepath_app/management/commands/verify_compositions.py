"""Audit virtual-fund compositions: each fund's category percentages must sum to 100%.

Usage:
    python manage.py verify_compositions
    python manage.py verify_compositions --provider nysaves

Exits non-zero if any active fund fails, so it can be used in CI / pre-deploy checks.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from glidepath_app.models import VirtualFund


class Command(BaseCommand):
    help = "Verify that every virtual fund's composition percentages sum to 100%."

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider", help="Limit the audit to a single provider slug (e.g. nysaves)."
        )
        parser.add_argument(
            "--include-inactive", action="store_true",
            help="Also audit funds where is_active is False.",
        )

    def handle(self, *args, **options):
        funds = VirtualFund.objects.select_related("provider").prefetch_related("composition")
        if options.get("provider"):
            funds = funds.filter(provider__slug=options["provider"])
        if not options.get("include_inactive"):
            funds = funds.filter(is_active=True)

        problems = []
        checked = 0
        for fund in funds:
            checked += 1
            total = sum(
                (c.percentage for c in fund.composition.all()), Decimal("0")
            )
            if total != Decimal("100"):
                problems.append((fund, total, fund.composition.count()))

        if problems:
            self.stderr.write(self.style.ERROR(
                f"{len(problems)} of {checked} virtual fund(s) have invalid compositions:"
            ))
            for fund, total, count in problems:
                detail = f"sums to {total}%" if count else "has no composition rows"
                self.stderr.write(f"  - {fund.provider.slug}:{fund.slug} ({fund.name}) {detail}")
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(
            f"All {checked} virtual fund composition(s) sum to 100%."
        ))
