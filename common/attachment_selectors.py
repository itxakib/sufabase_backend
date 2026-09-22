"""Tenant-scoped lookups for ``common.Attachment``.

Same rule as every other selector in this project: the tenant is an explicit
parameter, never a thread-local and never inferred from the request.

The generic foreign key makes that rule easy to forget here, because an
attachment *looks* scoped by whatever it hangs off. It is not: nothing in the
schema ties ``content_type``/``object_id`` to a company, so a query that skips
the ``company`` filter happily returns another tenant's passport scan. The
filter is written once, here, and every caller is told the tenant.
"""

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count

from common.models import Attachment


class AttachmentSelector:
    """Query building for any model's attachments."""

    @staticmethod
    def for_company(company, *, content_type=None, object_id=None, doc_type=None):
        """Every attachment this tenant owns, optionally narrowed.

        ``company`` accepts a ``Company`` instance or a primary key. There is no
        ``company=None`` escape hatch - an unfiltered attachment query is a data
        leak, not a convenience.
        """
        queryset = Attachment.objects.filter(company=company).select_related(
            'content_type', 'created_by',
        )
        if content_type is not None:
            queryset = queryset.filter(content_type=content_type)
        if object_id is not None:
            queryset = queryset.filter(object_id=object_id)
        if doc_type:
            queryset = queryset.filter(doc_type__icontains=doc_type)
        return queryset.order_by('-created_at')

    @staticmethod
    def for_object(obj, company):
        """The documents hanging off one specific record.

        ``obj`` is trusted only for its identity (its class and primary key);
        the tenant still comes from the explicit ``company`` argument, so a
        caller that resolved the wrong object cannot widen the result set.

        ``select_related('created_by')`` because every caller renders who
        uploaded the file, and that must not be one query per row.
        """
        return AttachmentSelector.for_company(
            company,
            content_type=ContentType.objects.get_for_model(obj, for_concrete_model=False),
            object_id=obj.pk,
        )

    @staticmethod
    def count_for_object(obj, company):
        """How many documents hang off one record - without loading them.

        Used by anything that shows "3 documents" and only fetches the rows
        when the user actually opens the panel.
        """
        return AttachmentSelector.for_object(obj, company).count()

    @staticmethod
    def counts_for_objects(model_cls, object_ids, company):
        """``{object_id: count}`` for many records in **one** query.

        The batched form of :meth:`count_for_object`, for the same reason
        ``TenantScopedSelector.counts_by_customer`` exists: calling the singular
        version once per row on a 25-row page is 25 round trips to render a
        number that a single ``GROUP BY`` already knows. Records with no
        attachments are absent from the result, so callers default them to 0.
        """
        ids = list(object_ids)
        if not ids:
            return {}
        rows = (
            Attachment.objects
            .filter(
                company=company,
                content_type=ContentType.objects.get_for_model(
                    model_cls, for_concrete_model=False,
                ),
                object_id__in=ids,
            )
            .values('object_id')
            .annotate(total=Count('pk'))
        )
        return {row['object_id']: row['total'] for row in rows}
