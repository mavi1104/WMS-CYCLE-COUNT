from getpass import getpass

from django.core.management.base import BaseCommand, CommandError

from cycle_counts.serializers import CounterAccountSerializer


class Command(BaseCommand):
    help = "Create a WMS administrator in mobile_counter_accounts using an interactive password prompt."

    # Register the required --username and --name arguments for create_wms_admin.
    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--name", required=True)

    # Confirm the password and create an administrator through the serializer. Troubleshoot: matching passwords and validation errors.
    def handle(self, *args, **options):
        password = getpass("Password: ")
        if password != getpass("Confirm password: "):
            raise CommandError("Passwords do not match.")
        serializer = CounterAccountSerializer(data={
            "name": options["name"], "username": options["username"],
            "password": password, "role": "admin", "active": True,
        })
        if not serializer.is_valid():
            raise CommandError(str(serializer.errors))
        account = serializer.save()
        self.stdout.write(self.style.SUCCESS(f"Administrator '{account.username}' created. Sign in at /login."))
