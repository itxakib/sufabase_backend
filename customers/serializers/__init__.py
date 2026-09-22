from customers.serializers.customer import (
    CustomerDetailSerializer,
    CustomerListSerializer,
    CustomerMiniSerializer,
    CustomerWriteSerializer,
    TagSerializer,
)

# Backward-compatible alias — the old view still references CustomerSerializer
CustomerSerializer = CustomerDetailSerializer

__all__ = [
    "CustomerDetailSerializer",
    "CustomerListSerializer",
    "CustomerMiniSerializer",
    "CustomerWriteSerializer",
    "CustomerSerializer",
    "TagSerializer",
]
