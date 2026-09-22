from django.conf import settings
from django.db import models


class AuditModel(models.Model):
    """Adds explicit created_by / updated_by attribution.

    Both fields are nullable on purpose:

    * the first company and the first user in the system have no creator;
    * deleting a staff account must never cascade-delete the business records
      they touched, hence SET_NULL.

    ``editable=False`` keeps them out of ModelForms, Django admin forms, and
    DRF-generated serializer fields, so they can never be client-supplied.
    They are written explicitly by the service that performs the write - this
    codebase deliberately uses no signals, middleware, or thread-local current
    user to fill them in.
    """

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        editable=False,
        related_name='%(app_label)s_%(class)s_created',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        editable=False,
        related_name='%(app_label)s_%(class)s_updated',
    )

    class Meta:
        abstract = True
