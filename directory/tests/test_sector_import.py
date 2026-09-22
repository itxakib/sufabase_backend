"""The sector title is read from the Name column of a marker row.

The LCCI workbook puts ``Business Sector:`` in the company column and the
sector name in the next column (Name). The Sub Sector column on that row is
blank. Reading the blank cell stored every company with an empty
``business_sector``, which is why the sector dropdown only offered "All".
"""

from django.test import TestCase

from common.tests.factories import make_company
from directory.models import DirectoryCompany
from directory.services import DirectoryImportService


class _Cell:
    def __init__(self, value):
        self.value = value


class _Sheet:
    def __init__(self, rows):
        self._rows = rows
        self.nrows = len(rows)
        self.ncols = len(rows[0])

    def cell(self, row, col):
        return _Cell(self._rows[row][col])


HEADERS = [
    'Sr No', 'Company', 'Name', 'Sub Sector', 'Address', 'Product Line',
    'EMail', 'Url', 'Ph. No', 'M.Ship #', 'M.type',
]


def _row(*cells):
    padded = list(cells) + [''] * (11 - len(cells))
    return padded[:11]


class SectorMarkerImportTests(TestCase):
    def setUp(self):
        self.company = make_company(name='Alpha Travel', slug='alpha-travel')

    def test_marker_sector_comes_from_the_name_column(self):
        sheet = _Sheet([
            _row('', 'Manufacturers'),
            _row(*HEADERS),
            _row('', 'Business Sector:', 'AGRICULTURE & HORTICULTURE', ''),
            _row(
                '1', 'AGROMAX INTERNATIONAL', 'MR. ALI RAZA - Partner',
                'AGRICULTURAL CROPS & SEEDS', 'Lahore', 'Seeds',
                'ali@agromaxpk.com', '', '042', '130060', 'A',
            ),
        ])
        stats = {
            'total_rows': 0,
            'companies_created': 0,
            'companies_updated': 0,
            'activities_created': 0,
            'issues': [],
        }

        DirectoryImportService._import_sheet(
            sheet, 'Manufacturers', self.company, batch=None, stats=stats,
        )

        saved = DirectoryCompany.objects.get(membership_number='130060')
        self.assertEqual(saved.business_sector, 'AGRICULTURE & HORTICULTURE')
        self.assertEqual(saved.sub_sector, 'AGRICULTURAL CROPS & SEEDS')
        self.assertEqual(
            list(saved.activities.values_list('sheet_name', flat=True)),
            ['Manufacturers'],
        )
