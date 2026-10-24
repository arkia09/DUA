from django.core.management.base import BaseCommand

from ...wipe import wipe_cases


class Command(BaseCommand):
    help = "Delete every case and restart the case numbers."

    def handle(self, *args, **options):
        wipe_cases()
        self.stdout.write("All cases deleted.")
