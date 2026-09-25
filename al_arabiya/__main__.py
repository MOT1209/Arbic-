"""Allow ``python -m al_arabiya`` as an alias for the ``arabic`` CLI."""

import sys

from al_arabiya.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
