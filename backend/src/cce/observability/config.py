"""Engineering observability configuration."""

import os

LOG_LEVEL = os.environ.get("CCE_LOG_LEVEL", "INFO")
