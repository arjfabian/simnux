"""Custom log level definitions for SIMNUX observability.

Defines an intermediate "OK" level between INFO and WARNING for
positive operational signals.
"""

import logging


# Custom OK level (25) for positive operational signals that are more notable
# than INFO but not warnings. Example: scenario load success, session creation,
# command registration.
LOG_LEVEL_OK = 25

logging.addLevelName(LOG_LEVEL_OK, "OK")
