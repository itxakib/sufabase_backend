"""Consultancy models, one per file, exported in dependency order.

The abstract ``CaseRecordBase`` comes first, then the two concrete case models
that inherit it. Same layout as the ``bookings`` app, for the same reason: an
``__init__`` that reads in dependency order makes an import cycle obvious the
moment one appears.
"""

from consultancy.models.base import CaseRecordBase
from consultancy.models.visa_consultancy import VisaConsultancyCase
from consultancy.models.study_visa import StudyVisaCase

__all__ = [
    'CaseRecordBase',
    'VisaConsultancyCase',
    'StudyVisaCase',
]
