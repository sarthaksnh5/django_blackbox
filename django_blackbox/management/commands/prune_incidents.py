"""
Management command to prune old incidents.
"""
from django.core.management.base import BaseCommand
from django.db import models
from django.utils import timezone

from django_blackbox.conf import get_conf
from django_blackbox.models import Incident


class Command(BaseCommand):
    """Prune incidents older than retention period."""

    help = "Delete incidents older than the configured retention period (default 90 days)"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--older-than",
            type=int,
            help="Delete incidents older than this many days (overrides RETENTION_DAYS setting)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        older_than = options.get("older_than")
        dry_run = options.get("dry_run", False)
        
        # Get retention days from config or argument
        if older_than is None:
            config = get_conf()
            older_than = config.RETENTION_DAYS
        else:
            older_than = older_than
        
        # Calculate cutoff date
        cutoff = timezone.now() - timezone.timedelta(days=older_than)
        
        # Count incidents to delete
        queryset = Incident.objects.filter(occurred_at__lt=cutoff)
        count = queryset.count()
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"No incidents found older than {older_than} days."
                )
            )
            return
        
        # Show what would be deleted
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] Would delete {count} incidents older than {older_than} days "
                    f"(before {cutoff.strftime('%Y-%m-%d %H:%M:%S %Z')})"
                )
            )
            return
        
        # Actually delete
        self.stdout.write(
            self.style.WARNING(f"Deleting {count} incidents older than {older_than} days...")
        )
        
        # Group by status for reporting
        status_counts = queryset.values("status").annotate(
            count=models.Count("id")
        )
        
        # Delete
        deleted, _ = queryset.delete()
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully deleted {deleted} incidents."
            )
        )
        
        # Show breakdown by status
        if status_counts:
            self.stdout.write("\nBreakdown by status:")
            for item in status_counts:
                self.stdout.write(
                    f"  {item['status']}: {item['count']}"
                )

