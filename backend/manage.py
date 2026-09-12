#!/usr/bin/env python
import os
import sys


# Start the Django management command. Troubleshoot: installed requirements and DJANGO_SETTINGS_MODULE.
def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wms_api.settings")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django is not installed. Install backend/requirements.txt first."
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

