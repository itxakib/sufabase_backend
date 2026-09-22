from django.db import models


class TimeStampedModel(models.Model):
    """Adds creation/update timestamps.

    Use this standalone for models that need timestamps but no user
    attribution, e.g. lookup or join tables.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
