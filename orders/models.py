import uuid
from django.db import models, transaction
from django.conf import settings
from products.models import Product

class Order(models.Model):
    class OrderStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PROCESSING = 'PROCESSING', 'Processing'
        PACKAGING = 'PACKAGING', 'Packaging' # Added for more steps
        SHIPPED = 'SHIPPED', 'Shipped'
        DELIVERED = 'DELIVERED', 'Delivered'
        CANCELED = 'CANCELED', 'Canceled'
        FAILED = 'FAILED', 'Failed' # For issues like stock unavailability or payment failure

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer_name = models.CharField(max_length=255) # Simplified customer info
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
    )
    # For stale order detection, we need to know which task is expected next
    expected_next_task_eta = models.DateTimeField(null=True, blank=True, db_index=True)


    def __str__(self):
        return f"Order {self.id} - {self.status}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name='order_items', on_delete=models.PROTECT) # Protect product from deletion if in order
    quantity = models.PositiveIntegerField()
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2) # Store price at time of order

    class Meta:
        unique_together = ('order', 'product') # Prevent duplicate products in the same order

    def __str__(self):
        return f"{self.quantity} x {self.product.sku} for Order {self.order.id}"

class OrderHistory(models.Model):
    order = models.ForeignKey(Order, related_name='history', on_delete=models.CASCADE)
    from_status = models.CharField(max_length=20, choices=Order.OrderStatus.choices, null=True, blank=True)
    to_status = models.CharField(max_length=20, choices=Order.OrderStatus.choices)
    timestamp = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"Order {self.order.id}: {self.from_status} -> {self.to_status} at {self.timestamp}"

# Utility function to log history and update status
def update_order_status(order: Order, new_status: Order.OrderStatus, notes: str = None, expected_eta_delta_seconds: int = None):
    """
    Updates order status, logs history, and sets expected ETA for the next task if applicable.
    """
    from django.utils import timezone
    import datetime

    old_status = order.status
    order.status = new_status

    if expected_eta_delta_seconds:
        order.expected_next_task_eta = timezone.now() + datetime.timedelta(seconds=expected_eta_delta_seconds)
    else:
        # Clear ETA if it's a terminal state or next step is immediate
        order.expected_next_task_eta = None

    order.save(update_fields=['status', 'updated_at', 'expected_next_task_eta'])
    OrderHistory.objects.create(order=order, from_status=old_status, to_status=new_status, notes=notes)
    print(f"Order {order.id} status updated from {old_status} to {new_status}")