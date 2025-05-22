from rest_framework import serializers

from .models import Inventory, Product


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'sku', 'description', 'price']

class InventorySerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True) # Show product details
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source='product', write_only=True
    )

    class Meta:
        model = Inventory
        fields = ['id', 'product', 'product_id', 'stock_level', 'last_updated']
        read_only_fields = ['last_updated']