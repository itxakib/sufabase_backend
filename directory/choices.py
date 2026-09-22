"""Choice enumerations for the directory app.

Import statuses only — the LCCI source file's own columns (membership types,
sheet names, sector names) are free text because future directory exports may
use different values. Restricting them here would break the next import.
"""

from django.db import models


class ImportStatusChoices(models.TextChoices):
    """Lifecycle of an import batch, tracked from the moment the file arrives."""
    PENDING = 'PENDING', 'Pending'
    PROCESSING = 'PROCESSING', 'Processing'
    COMPLETED = 'COMPLETED', 'Completed'
    FAILED = 'FAILED', 'Failed'
