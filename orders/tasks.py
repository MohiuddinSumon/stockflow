import datetime
import random
import time

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from products.models import Inventory  # Import Inventory model

from .models import Order, OrderItem, Product, update_order_status


def get_simulated_delay(min_delay, max_delay):
    return random.uniform(min_delay, max_delay)

@shared_task(bind=True, max_retries=3, default_retry_delay=60) # Added retry mechanism
def process_order_task(self, order_id):
    try:
        order = Order.objects.get(id=order_id)
        if order.status != Order.OrderStatus.PENDING:
            print(f"Order {order_id} is not PENDING, skipping process_order_task. Current status: {order.status}")
            return

        print(f"Task: Processing order {order_id}")
        # Simulate initial processing / payment validation
        time.sleep(get_simulated_delay(settings.ORDER_PROCESSING_DELAY_MIN / 2, settings.ORDER_PROCESSING_DELAY_MAX / 2))

        update_order_status(
            order,
            Order.OrderStatus.PROCESSING,
            notes="Order validation started.",
            expected_eta_delta_seconds=int(settings.ORDER_PROCESSING_DELAY_MAX * 1.5) # Time for inventory check + packaging
        )

        # --- Inventory Check and Allocation ---
        try:
            with transaction.atomic():
                order_items_to_check = order.items.select_related('product').all()
                unavailable_items = []

                for item in order_items_to_check:
                    # Lock the inventory row for this product to prevent race conditions
                    inventory = Inventory.objects.select_for_update().get(product=item.product)
                    if inventory.stock_level < item.quantity:
                        unavailable_items.append(f"{item.product.name} (requested: {item.quantity}, available: {inventory.stock_level})")
                    else:
                        # Decrement stock atomically
                        Inventory.objects.filter(pk=inventory.pk, stock_level__gte=item.quantity).update(stock_level=F('stock_level') - item.quantity)
                        # Re-fetch to confirm update (or check rows_updated from .update())
                        inventory.refresh_from_db()
                        if inventory.stock_level < 0: # Should not happen with gte filter but as a safeguard
                             raise Exception(f"Concurrency issue: Stock for {item.product.name} went negative.")


                if unavailable_items:
                    error_message = f"Insufficient stock for items: {', '.join(unavailable_items)}"
                    print(f"Order {order_id}: {error_message}")
                    update_order_status(order, Order.OrderStatus.FAILED, notes=error_message)
                    return # Stop processing this order

        except Inventory.DoesNotExist:
            update_order_status(order, Order.OrderStatus.FAILED, notes="Critical error: Inventory record missing for a product.")
            return
        except Exception as e: # Catch broader exceptions during inventory logic
            print(f"Error during inventory check for order {order_id}: {e}")
            update_order_status(order, Order.OrderStatus.FAILED, notes=f"Inventory processing error: {e}")
            # Potentially retry if it's a transient DB issue, but for stock issues, it's usually a fail
            # self.retry(exc=e) # Be cautious with retrying inventory logic
            return

        # If all items available and stock decremented
        print(f"Order {order_id}: Inventory allocated.")
        update_order_status(
            order,
            Order.OrderStatus.PACKAGING,
            notes="Inventory allocated, order is being packaged.",
            expected_eta_delta_seconds=int(settings.ORDER_SHIPPING_DELAY_MAX * 1.5) # Time for packaging + shipping
        )
        # Simulate packaging
        time.sleep(get_simulated_delay(settings.ORDER_PROCESSING_DELAY_MIN / 2, settings.ORDER_PROCESSING_DELAY_MAX / 2))

        # Enqueue next task (shipping)
        ship_order_task.delay(order.id)

    except Order.DoesNotExist:
        print(f"Order {order_id} not found in process_order_task.")
    except Exception as exc:
        print(f"Error processing order {order_id}: {exc}")
        try:
            order = Order.objects.get(id=order_id)
            update_order_status(order, Order.OrderStatus.FAILED, notes=f"Unhandled exception in processing: {exc}")
        except Order.DoesNotExist:
            pass # Order not found, nothing to update
        self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def ship_order_task(self, order_id):
    try:
        order = Order.objects.get(id=order_id)
        if order.status != Order.OrderStatus.PACKAGING:
            print(f"Order {order_id} is not PACKAGING, skipping ship_order_task. Current status: {order.status}")
            return

        print(f"Task: Shipping order {order_id}")
        update_order_status(
            order,
            Order.OrderStatus.SHIPPED,
            notes="Order has been shipped.",
            expected_eta_delta_seconds=int(settings.ORDER_DELIVERY_DELAY_MAX * 1.5) # Time for delivery
        )
        time.sleep(get_simulated_delay(settings.ORDER_SHIPPING_DELAY_MIN, settings.ORDER_SHIPPING_DELAY_MAX))

        # Enqueue next task (delivery)
        deliver_order_task.delay(order.id)

    except Order.DoesNotExist:
        print(f"Order {order_id} not found in ship_order_task.")
    except Exception as exc:
        print(f"Error shipping order {order_id}: {exc}")
        try:
            order = Order.objects.get(id=order_id)
            update_order_status(order, Order.OrderStatus.FAILED, notes=f"Unhandled exception in shipping: {exc}")
        except Order.DoesNotExist:
            pass
        self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=180)
def deliver_order_task(self, order_id):
    try:
        order = Order.objects.get(id=order_id)
        if order.status != Order.OrderStatus.SHIPPED:
            print(f"Order {order_id} is not SHIPPED, skipping deliver_order_task. Current status: {order.status}")
            return

        print(f"Task: Delivering order {order_id}")
        # No next ETA for delivered status
        update_order_status(order, Order.OrderStatus.DELIVERED, notes="Order has been delivered.")
        time.sleep(get_simulated_delay(settings.ORDER_DELIVERY_DELAY_MIN, settings.ORDER_DELIVERY_DELAY_MAX))
        print(f"Order {order_id} successfully delivered.")

    except Order.DoesNotExist:
        print(f"Order {order_id} not found in deliver_order_task.")
    except Exception as exc:
        print(f"Error delivering order {order_id}: {exc}")
        try:
            order = Order.objects.get(id=order_id)
            update_order_status(order, Order.OrderStatus.FAILED, notes=f"Unhandled exception in delivery: {exc}")
        except Order.DoesNotExist:
            pass
        self.retry(exc=exc)


# --- Stale Order Handling Task (triggered by Celery Beat) ---
@shared_task
def detect_and_handle_stale_orders():
    print("Running stale order detection task...")
    stale_threshold_time = timezone.now() - datetime.timedelta(minutes=settings.STALE_ORDER_THRESHOLD_MINUTES)

    # Find orders in transitional states that haven't been updated recently
    # AND where their expected_next_task_eta has passed
    stale_orders = Order.objects.filter(
        status__in=[
            Order.OrderStatus.PENDING,
            Order.OrderStatus.PROCESSING,
            Order.OrderStatus.PACKAGING,
            Order.OrderStatus.SHIPPED,
        ],
        # updated_at__lt=stale_threshold_time, # Alternative: check if updated_at is old
        expected_next_task_eta__lt=timezone.now() # Check if expected ETA has passed
    ).exclude(expected_next_task_eta__isnull=True) # Only consider orders with an ETA

    if not stale_orders.exists():
        print("No stale orders found.")
        return

    print(f"Found {stale_orders.count()} potentially stale orders.")
    for order in stale_orders:
        print(f"Stale order detected: {order.id}, Status: {order.status}, Expected ETA: {order.expected_next_task_eta}, Last Updated: {order.updated_at}")

        # Basic resolution: Mark as FAILED.
        # More sophisticated: Could try to re-queue the appropriate task if idempotent,
        # or escalate to a manual review queue.
        # For this simulation, we'll mark as FAILED.
        update_order_status(
            order,
            Order.OrderStatus.FAILED,
            notes=f"Order automatically marked as FAILED due to being stale. Last status: {order.status}. Expected ETA: {order.expected_next_task_eta}."
        )
        print(f"Order {order.id} marked as FAILED due to staleness.")

        # Example of re-queuing (use with caution, ensure tasks are idempotent)
        # if order.status == Order.OrderStatus.PENDING or order.status == Order.OrderStatus.PROCESSING:
        #     print(f"Re-queueing process_order_task for stale order {order.id}")
        #     process_order_task.delay(order.id) # This might lead to loops if not careful
        # elif order.status == Order.OrderStatus.PACKAGING:
        #     # (Assuming process_order_task moves it to PACKAGING, then ship_order_task is next)
        #     print(f"Re-queueing ship_order_task for stale order {order.id}")
        #     ship_order_task.delay(order.id)
        # elif order.status == Order.OrderStatus.SHIPPED:
        #     print(f"Re-queueing deliver_order_task for stale order {order.id}")
        #     deliver_order_task.delay(order.id)