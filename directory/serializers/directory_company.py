from rest_framework import serializers
from directory.models import DirectoryCompany


class DirectoryCompanyListSerializer(serializers.ModelSerializer):
    """Lightweight — for the directory table/list view."""
    activity_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = DirectoryCompany
        fields = [
            'id', 'membership_number', 'company_name', 'contact_person',
            'business_sector', 'sub_sector', 'email', 'phone',
            'membership_type', 'activity_count',
            'created_at',
        ]


class DirectoryCompanyDetailSerializer(serializers.ModelSerializer):
    """Full detail — includes address and product line."""
    activity_count = serializers.IntegerField(read_only=True)
    activities = serializers.SerializerMethodField()

    class Meta:
        model = DirectoryCompany
        fields = [
            'id', 'membership_number', 'membership_type', 'company_name',
            'contact_person', 'business_sector', 'sub_sector', 'address',
            'product_line', 'email', 'website', 'phone',
            'converted_customer', 'converted_at',
            'activity_count', 'activities',
            'created_at', 'updated_at',
        ]

    def get_activities(self, obj) -> list:
        from directory.serializers.import_batch import (
            DirectoryBusinessActivitySerializer,
        )
        return DirectoryBusinessActivitySerializer(
            obj.activities.all(), many=True,
        ).data
