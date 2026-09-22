"""Serializers for the sector lookup the list filters are built from.

These describe a *computed* payload — distinct values read back out of the
directory — rather than a model, so they are plain ``Serializer`` subclasses.
They exist so the endpoint has a real OpenAPI schema: the frontend's option types
are generated from the schema, and an untyped dict response would reach the
browser as ``unknown``.
"""

from rest_framework import serializers


class DirectorySubSectorSerializer(serializers.Serializer):
    """One sub-sector recorded under a top-level sector."""

    value = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()


class DirectoryActivityOptionSerializer(serializers.Serializer):
    """One chamber sheet (Manufacturers, Importers, …) the activity filter offers."""

    value = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()


class DirectorySectorSerializer(serializers.Serializer):
    """One top-level sector and every sub-sector recorded beneath it."""

    value = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()
    sub_sectors = DirectorySubSectorSerializer(many=True)
