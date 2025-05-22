from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import transaction
from .models import Order, OrderItem, OrderHistory, Product, update_order_status
from .serializers import (
    OrderSerializer, OrderHistorySerializer,
    BulkOrderRequestItemSerializer, BulkOrderResponseItemSerializer
)
from .tasks import process_order_task

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.prefetch_related('items', 'history').all().order_by('-created_at')
    serializer_class = OrderSerializer

    def get_serializer_class(self):
        if self.action == 'create_bulk':
            return BulkOrderRequestItemSerializer # For input
        return super().get_serializer_class()

    # Standard create is for single order
    def perform_create(self, serializer):
        # The logic is now in OrderSerializer.create() to trigger Celery task
        serializer.save()

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        order = self.get_object()
        history_qs = order.history.all()
        serializer = OrderHistorySerializer(history_qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='bulk')
    def create_bulk(self, request):
        """
        Accepts a list of order creation requests.
        Processes each individually and returns a list of results.
        """
        bulk_request_serializer = BulkOrderRequestItemSerializer(data=request.data, many=True)
        if not bulk_request_serializer.is_valid():
            return Response(bulk_request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_orders_data = bulk_request_serializer.validated_data
        results = []
        created_order_ids = []

        for order_data in validated_orders_data:
            # This re-uses the OrderSerializer's create logic internally
            # which includes transaction management and task queuing for each order.
            # However, for bulk, we want to manage the transaction at a higher level if possible
            # or just process them one by one. For now, let's do one by one.

            # We'll manually construct the order and items to control the flow better for bulk
            customer_name = order_data.get('customer_name')
            items_data = order_data.get('items')

            if not customer_name or not items_data:
                results.append({
                    "customer_name": customer_name or "N/A",
                    "status": "VALIDATION_ERROR",
                    "message": "Missing customer_name or items."
                })
                continue

            try:
                with transaction.atomic(): # Transaction for each individual order in the bulk request
                    order = Order.objects.create(customer_name=customer_name)
                    # Log initial PENDING state
                    update_order_status(
                        order, Order.OrderStatus.PENDING, "Order created via bulk request.",
                        expected_eta_delta_seconds=30 # Initial small ETA
                    )

                    for item_data in items_data:
                        product = item_data['product'] # product object resolved by serializer
                        OrderItem.objects.create(
                            order=order,
                            product=product,
                            quantity=item_data['quantity'],
                            price_at_purchase=product.price
                        )
                    process_order_task.delay(order.id)
                    created_order_ids.append(order.id)
                    results.append({
                        "order_id": order.id,
                        "customer_name": order.customer_name,
                        "status": "ACCEPTED",
                        "message": "Order accepted and processing initiated."
                    })
            except Exception as e:
                # Log the exception e
                results.append({
                    "customer_name": customer_name,
                    "status": "CREATION_FAILED",
                    "message": f"Failed to create order: {str(e)}"
                })

        response_serializer = BulkOrderResponseItemSerializer(data=results, many=True)
        response_serializer.is_valid() # Should be valid as we construct it
        return Response(response_serializer.data, status=status.HTTP_207_MULTI_STATUS)