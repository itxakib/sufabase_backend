"""Create Hajj bookings from a two-column CSV.

Each row is an application id and a passport number. The passport is matched
to a customer this company already has; a row whose passport is not on file
is reported and skipped. The import never creates a customer.
"""

import csv
import io
import re

from django.db import transaction
from django.utils import timezone

from bookings.models import HajjBooking
from bookings.utils import generate_booking_reference
from customers.models import Customer

# Spreadsheet headers people actually type, folded onto the two fields we read.
_HEADER_FIELDS = {
    'application_number': 'application_number',
    'application_id': 'application_number',
    'hajj_application_id': 'application_number',
    'hajj_application_number': 'application_number',
    'passport_number': 'passport_number',
    'passport': 'passport_number',
    'passport_no': 'passport_number',
}

_REQUIRED = ('application_number', 'passport_number')


def normalize_passport(value):
    """Compare passports ignoring case, spaces and hyphens."""
    return re.sub(r'[^A-Za-z0-9]', '', value or '').upper()


def _header_key(name):
    cleaned = re.sub(r'[^a-z0-9]+', '_', (name or '').strip().lower()).strip('_')
    return _HEADER_FIELDS.get(cleaned)


def import_hajj_applications(company, user, decoded_csv, hajj_year):
    """Import one CSV.

    Returns ``(report, error)``. ``error`` is a string when the file itself
    cannot be read (missing columns); row problems live in ``report['errors']``
    and do not reject the rows that matched.
    """
    reader = csv.DictReader(io.StringIO(decoded_csv))
    if not reader.fieldnames:
        return None, 'CSV file is empty or has no headers.'

    columns = {}
    for header in reader.fieldnames:
        field = _header_key(header)
        if field and field not in columns:
            columns[field] = header

    missing = [field for field in _REQUIRED if field not in columns]
    if missing:
        return None, (
            f'Missing required columns: {", ".join(missing)}. '
            'Download the template for the correct headers.'
        )

    passport_owners, ambiguous = _passport_index(company)
    taken = {
        application_number: customer_id
        for customer_id, application_number in HajjBooking.objects.filter(company=company)
        .exclude(application_number='')
        .values_list('customer_id', 'application_number')
    }

    errors = []
    skipped = 0
    created = 0
    total_rows = 0
    seen_in_file = {}
    package_name = f'Hajj {hajj_year}'

    with transaction.atomic():
        for row_index, row in enumerate(reader, start=1):
            application_number = (row.get(columns['application_number']) or '').strip()
            passport_raw = (row.get(columns['passport_number']) or '').strip()
            if not application_number and not passport_raw:
                continue

            total_rows += 1
            row_errors = {}
            if not application_number:
                row_errors['application_number'] = 'application_number is required.'
            elif len(application_number) > 100:
                row_errors['application_number'] = 'application_number is longer than 100 characters.'

            passport_key = normalize_passport(passport_raw)
            if not passport_raw:
                row_errors['passport_number'] = 'passport_number is required.'
            elif passport_key in ambiguous:
                row_errors['passport_number'] = (
                    'More than one customer has this passport number.'
                )
            elif passport_key not in passport_owners:
                row_errors['passport_number'] = (
                    'No customer has this passport number.'
                )

            if row_errors:
                errors.append({'row': row_index, 'errors': row_errors})
                continue

            customer = passport_owners[passport_key]
            owner_id = taken.get(application_number)
            if owner_id == customer.pk or seen_in_file.get(application_number) == customer.pk:
                skipped += 1
                continue
            if owner_id is not None or application_number in seen_in_file:
                errors.append({
                    'row': row_index,
                    'errors': {
                        'application_number': (
                            'This application id is already on another customer.'
                        ),
                    },
                })
                continue

            reference = generate_booking_reference(HajjBooking, company)
            HajjBooking.objects.create(
                company=company,
                created_by=user,
                customer=customer,
                hajj_year=hajj_year,
                application_number=application_number,
                package_name=package_name,
                booking_reference=reference,
            )
            taken[application_number] = customer.pk
            seen_in_file[application_number] = customer.pk
            created += 1

    return {
        'total_rows': total_rows,
        'created': created,
        'skipped': skipped,
        'hajj_year': hajj_year,
        'errors': errors,
    }, None


def _passport_index(company):
    """Map a normalised passport to the one customer who holds it.

    A passport shared by two customers is recorded as ambiguous and left out
    of the map, so the import refuses to guess which person the row means.
    """
    owners = {}
    ambiguous = set()
    rows = (
        Customer.objects.filter(company=company)
        .exclude(passport_number='')
        .only('id', 'passport_number')
    )
    for customer in rows:
        key = normalize_passport(customer.passport_number)
        if not key:
            continue
        if key in owners or key in ambiguous:
            owners.pop(key, None)
            ambiguous.add(key)
            continue
        owners[key] = customer
    return owners, ambiguous


def default_hajj_year():
    return str(timezone.now().year)
