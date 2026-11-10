from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from reference_data.importer import DEFAULT_MANIFEST, ImportFileError, import_manifest
from reference_data.models import BenchmarkCase


class Command(BaseCommand):
    help = (
        "Import historical benchmark cases (default: the bundled TravelPlanner dataset). "
        "Repeated imports update existing cases instead of duplicating them."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "manifest",
            nargs="?",
            default=str(DEFAULT_MANIFEST),
            help="Path to a manifest.json (default: bundled TravelPlanner data).",
        )
        parser.add_argument(
            "--split",
            action="append",
            choices=BenchmarkCase.Split.values,
            help="Only import this split. Can be given several times.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and compare with the database without writing anything.",
        )

    def handle(self, *args, manifest, split, dry_run, **options):
        try:
            report = import_manifest(Path(manifest), set(split) if split else None, dry_run)
        except ImportFileError as exc:
            raise CommandError(str(exc)) from exc

        for message in report.rejected:
            self.stderr.write(f"Rejected {message}")
        for name, count in report.per_split.items():
            self.stdout.write(f"  {name}: {count} valid cases")

        prefix = "Dry run, nothing written. Checked" if dry_run else "Imported"
        self.stdout.write(
            f"{prefix} {report.imported} cases ({report.created} new, {report.updated} updated, "
            f"{report.unchanged} unchanged), rejected {len(report.rejected)}."
        )
        if report.rejected:
            raise CommandError(
                f"{len(report.rejected)} invalid cases were rejected; "
                + ("see above." if dry_run else "the valid cases were imported.")
            )
