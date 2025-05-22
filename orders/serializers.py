from rest_framework import serializers
from django.db import transaction
from .models import Order, OrderItem, OrderHistory, Product, update_order_status
from products.serializers import ProductSerializer
from .tasks import process_order_task

class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), source='product')
    product = ProductSerializer(read_only=True) # For displaying product details

    class Meta:
        model = OrderItem
        fields = ['id', 'product_id', 'product', 'quantity', 'price_at_purchase']
        read_only_fields = ['price_at_purchase'] # Price is set server-side

class OrderHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderHistory
        fields = ['from_status', 'to_status', 'timestamp', 'notes']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    history = OrderHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'customer_name', 'status', 'created_at', 'updated_at', 'items', 'history', 'expected_next_task_eta']
        read_only_fields = ['id', 'status', 'created_at', 'updated_at', 'history', 'expected_next_task_eta']

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        with transaction.atomic(): # Ensure order and items are created together
            order = Order.objects.create(**validated_data)
            # Log initial PENDING state
            update_order_status(order, Order.OrderStatus.PENDING, "Order created.",
                                expected_eta_delta_seconds=30) # Initial small ETA for processing start

            for item_data in items_data:
                product = item_data['product']
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=item_data['quantity'],
                    price_at_purchase=product.price # Capture current price
                )
            # Kick off the asynchronous processing
            process_order_task.delay(order.id)
        return order

class BulkOrderRequestItemSerializer(serializers.Serializer): # For input of bulk orders
    customer_name = serializers.CharField(max_length=255)
    items = OrderItemSerializer(many=True) # Re-use item serializer structure

class BulkOrderResponseItemSerializer(serializers.Serializer):
    order_id = serializers.UUIDField(read_only=True)
    customer_name = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True) # e.g., "ACCEPTED" or "FAILED_VALIDATION"
    message = serializers.CharField(read_only=True, required=False)