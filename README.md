# Distributed Order Fulfillment System Simulation

This project simulates a distributed order fulfillment workflow using Django, Celery, and PostgreSQL.
It demonstrates handling concurrency, asynchronous workflows, lifecycle tracking, and stale state management.

## Architecture Overview

*   **Backend Framework:** Django with Django REST Framework (DRF) for APIs.
*   **Database:** PostgreSQL for relational data storage, transactions, and atomic operations.
*   **Asynchronous Task Queue:** Celery with Redis as the message broker. Used for:
    *   Order lifecycle progression (e.g., PENDING -> PROCESSING -> SHIPPED -> DELIVERED) with simulated delays.
    *   Handling potentially long-running operations without blocking API responses.
*   **Periodic Tasks:** Celery Beat for scheduling tasks like stale order detection.

**Key Components:**

*   **`products` app:** Manages product listings and inventory stock levels.
*   **`orders` app:** Manages order creation, lifecycle, history, and bulk processing.

## Design Decisions & Key Features

### 1. Product & Inventory Management
*   **Models:** `Product` (name, SKU, price), `Inventory` (product FK, stock_level).
*   **Atomicity:** Stock updates during order processing use `F()` expressions and `select_for_update` within database transactions to ensure consistency and prevent race conditions (e.g., overselling).
    *   `Inventory.objects.filter(pk=inventory.pk, stock_level__gte=item.quantity).update(stock_level=F('stock_level') - item.quantity)`
    *   The `stock_level__gte=item.quantity` condition in the filter ensures we don't decrement stock if it's insufficient, making the update conditional and atomic.

### 2. Order Lifecycle Workflow
*   **States:** PENDING → PROCESSING → PACKAGING → SHIPPED → DELIVERED. Also includes CANCELED and FAILED.
*   **Asynchronous Tasks:** Each major state transition (e.g., from PENDING to PROCESSING, PACKAGING to SHIPPED) is handled by a dedicated Celery task (`process_order_task`, `ship_order_task`, `deliver_order_task`).
*   **Simulated Delays:** `time.sleep()` with random durations (configured in `settings.py`) is used within tasks to simulate real-world processing times.
*   **Concurrency:** Celery workers can process multiple order tasks concurrently. Database-level locking (`select_for_update`) and atomic updates manage concurrent access to shared resources like inventory.

### 3. Bulk Order Processing
*   **API Endpoint:** `POST /api/orders/bulk/` accepts an array of order creation requests.
*   **Processing:** Each order in the bulk request is created as a separate `Order` record. The initial `process_order_task` is then enqueued for each newly created order.
*   **Response:** The API returns a `207 Multi-Status` response, indicating the acceptance status for each individual order within the bulk request. This allows the client to know which orders were successfully initiated and which failed validation/creation.

### 4. Stale Order Handling
*   **Detection:** A Celery Beat scheduled task (`detect_and_handle_stale_orders`) runs periodically (e.g., every minute for testing, configurable for production).
*   **Mechanism:**
    *   Orders have an `expected_next_task_eta` field. When a task completes and queues the next one, it estimates when that next task *should* have reasonably completed or at least started.
    *   The stale order detector queries for orders in transitional states (PENDING, PROCESSING, PACKAGING, SHIPPED) whose `expected_next_task_eta` has passed.
*   **Resolution:**
    *   Currently, stale orders are automatically transitioned to a `FAILED` state with a note.
    *   Future enhancements could include re-queueing the task (if idempotent), or flagging for manual review.
*   **Configuration:** `STALE_ORDER_THRESHOLD_MINUTES` in `settings.py` (used by the beat schedule to define how frequently to check, and the task itself could use it to define "staleness" if not using ETA). The `expected_next_task_eta` approach is more dynamic.

### 5. Order History Tracking
*   **Model:** `OrderHistory` (order FK, from_status, to_status, timestamp, notes).
*   **Mechanism:** A utility function `update_order_status(order, new_status, ...)` is called within Celery tasks whenever an order's status changes. This function updates the order's `status` and `expected_next_task_eta` fields and creates a new `OrderHistory` record. This ensures a complete audit trail of state transitions.

### 6. Throughput & Concurrency
*   **API Layer (Django/DRF):** Can be scaled horizontally by running multiple instances behind a load balancer (e.g., using Gunicorn/Uvicorn).
*   **Task Processing (Celery):** Celery workers can be scaled horizontally by running multiple worker processes across one or more machines. This allows the system to handle a high volume of asynchronous order processing tasks in parallel.
*   **Database (PostgreSQL):**
    *   Optimized queries (e.g., `select_related`, `prefetch_related` where appropriate).
    *   Proper indexing on frequently queried fields (e.g., `Order.status`, `Order.expected_next_task_eta`, foreign keys).
    *   Connection pooling (handled by Django).
    *   PostgreSQL itself is capable of handling high concurrency.
*   **Non-Blocking API:** Order creation APIs return quickly after validating input and enqueuing the first Celery task, rather than waiting for the entire order fulfillment process.

## Setup Instructions

1.  **Prerequisites:**
    *   Python 3.12+
    *   `uv` (Python package installer and virtual environment manager). Installation: `curl -LsSf https://astral.sh/uv/install.sh | sh` or `pip install uv` (if you have pip).
    *   PostgreSQL server installed and running.
    *   Redis server installed and running (for Celery broker).

2.  **Clone the repository (or create files as described):**
    ```bash
    git clone <your-repo-url>
    cd order_fulfillment_system
    ```

3.  **Ensure you have a `pyproject.toml` file** in the project root defining your dependencies. Example structure:
    ```toml
    [project]
    name = "order_fulfillment_system"
    version = "0.1.0"
    dependencies = [
        "Django>=4.2,<5.0",
        "djangorestframework>=3.14,<3.16",
        "psycopg2-binary>=2.9,<2.10",
        "celery>=5.3,<5.4",
        "redis>=5.0,<5.1",
        "python-dotenv>=1.0,<1.1",
        "drf-spectacular>=0.27,<0.28",
        # ... other dependencies
    ]
    [build-system]
    requires = ["hatchling"]
    build-backend = "hatchling.build"
    ```

4.  **Create a virtual environment using `uv`:**
    ```bash
    uv venv .venv  # Creates a virtual environment named .venv
    ```
    *Activation (`source .venv/bin/activate`) is optional if using `uv run` for all commands, but can still be useful for interactive sessions.*

5.  **Install dependencies using `uv` from `pyproject.toml`:**
    ```bash
    uv pip sync  # Preferred: Installs exact versions if a lock file exists
    # OR, if you don't have/use a lock file with 'sync' yet:
    # uv pip install .  # Installs the project and its dependencies
    ```
    *To generate a lock file (e.g., `requirements.lock`) from `pyproject.toml`:*
    ```bash
    uv pip compile pyproject.toml -o requirements.lock
    ```
    *Commit your `pyproject.toml` and the generated `requirements.lock` (or `uv.lock`).*

6.  **Configure Environment Variables:**
    *   Copy the example environment file: `cp .env.example .env`
    *   Edit the `.env` file and fill in your actual database credentials, secret key, and other configurations as needed.
    *   **Important:** Ensure `.env` is listed in your `.gitignore` file.

7.  **Configure Database:**
    *   Create a PostgreSQL database (e.g., `order_fulfillment_db`).
    *   Create a PostgreSQL user with permissions for this database.
    *   Ensure your `.env` file has the correct `DB_` variables set.
    *   For Database setup
        ```bash
            # DB Commands
            sudo -i -u postgres
            postgres@YOU:~$ psql
            psql (16.9 (Ubuntu 16.9-0ubuntu0.24.04.1))
            Type "help" for help.

            postgres=# create user DB_USER with password 'DBPASS';
            CREATE ROLE
            postgres=# create database PROJECT_DB owner DB_USER;
            CREATE DATABASE
            postgres=# GRANT ALL PRIVILEGES ON DATABASE PROJECT_DB TO DB_USER;
            GRANT
            postgres=# \q
            postgres@YOU:~$ exit
            logout
        ```

8.  **Apply Database Migrations:**
    ```bash
    uv run python manage.py makemigrations products orders
    uv run python manage.py migrate
    ```
    *Alternatively, if `manage.py` is executable (`chmod +x manage.py`):*
    ```bash
    uv run ./manage.py makemigrations products orders
    uv run ./manage.py migrate
    ```

9.  **Create a Django Superuser (optional, for admin panel access):**
    ```bash
    uv run python manage.py createsuperuser
    # Or: uv run ./manage.py createsuperuser
    ```

10. **Run the Development Server:**
    ```bash
    uv run python manage.py runserver
    # Or: uv run ./manage.py runserver
    ```
    The API will be accessible at `http://127.0.0.1:8000/api/`.
    The Django admin panel at `http://127.0.0.1:8000/admin/`.

11. **Run Celery Worker(s):**
    Open a new terminal.
    ```bash
    # On Linux/macOS:
    uv run celery -A backend_core worker -l info
    # On Windows (or if prefork issues arise):
    # uv run celery -A backend_core worker -l info -P eventlet
    ```

12. **Run Celery Beat (for scheduled tasks like stale order detection):**
    Open another new terminal.
    ```bash
    uv run celery -A backend_core beat -l info
    ```

## API Usage Examples

(Using `httpie` or `curl`)

### Products

*   **Create a Product:**
    ```bash
    http POST http://127.0.0.1:8000/api/products/ name="Laptop X1" sku="LPX1" description="Powerful laptop" price="1200.99"
    ```
*   **List Products:**
    ```bash
    http GET http://127.0.0.1:8000/api/products/
    ```
*   **Create/Update Inventory for a Product:**
    (Assuming product ID 1 exists)
    ```bash
    # Create inventory if it doesn't exist
    http POST http://127.0.0.1:8000/api/inventory/ product_id:=1 stock_level:=100
    # Update stock (using custom action on existing inventory ID, e.g., 1)
    http POST http://127.0.0.1:8000/api/inventory/1/update-stock/ stock_level:=90
    ```

### Orders

*   **Create a Single Order:**
    (Assuming product ID 1 exists and has stock)
    ```bash
    http POST http://127.0.0.1:8000/api/orders/ \
      customer_name="Alice Wonderland" \
      items:='[{"product_id": 1, "quantity": 2}]'
    ```
    *Response will include the new order ID and initial PENDING status.*

*   **Get Order Details (replace `<order_id>`):**
    ```bash
    http GET http://127.0.0.1:8000/api/orders/<order_id>/
    ```
    *Observe the `status` field change over time as Celery tasks process it.*

*   **Get Order History (replace `<order_id>`):**
    ```bash
    http GET http://127.0.0.1:8000/api/orders/<order_id>/history/
    ```

*   **Create Bulk Orders:**
    (Assuming product IDs 1 and 2 exist and have stock)
    ```bash
    http POST http://127.0.0.1:8000/api/orders/bulk/ < bulk_orders.json
    ```
    `bulk_orders.json`:
    ```json
    [
      {
        "customer_name": "Bob The Builder",
        "items": [
          {"product_id": 1, "quantity": 1},
          {"product_id": 2, "quantity": 5}
        ]
      },
      {
        "customer_name": "Charlie Chaplin",
        "items": [
          {"product_id": 1, "quantity": 3}
        ]
      }
    ]
    ```
    *Response will be a `207 Multi-Status` with individual results for each order.*

### Postman : Use API collection with postman

1.  **Access the Schema or UI:**
    *   **Schema URL:** `http://127.0.0.1:8000/api/schema/` (this will download a `schema.yml` or display JSON depending on your browser/Accept headers). You can also use `?format=openapi-json` for JSON.
    *   **Swagger UI:** `http://127.0.0.1:8000/api/schema/swagger-ui/`
    *   **ReDoc UI:** `http://127.0.0.1:8000/api/schema/redoc/`

2.  **Import into Postman:**
    *   Open Postman.
    *   Click on "Import" (usually in the top-left).
    *   you can download the `schema.yml` file from `http://127.0.0.1:8000/api/schema/` and then use the "File" tab in Postman's import dialog to upload it.

        Alternatively, Go to the "Link" tab. Paste the schema URL: `http://127.0.0.1:8000/api/schema/` (or `http://127.0.0.1:8000/api/schema/?format=openapi-json` if Postman prefers JSON directly, though it usually handles YAML fine from a URL). 
    *   Click "Continue" and follow the prompts. Postman will generate a collection based on your API schema.

    ![Postman Import Link](https://learning.postman.com/docs/getting-started/importing-data/importing-data-gifs/import-from-link.gif)
    *(This GIF shows the general idea of importing via link)*

3.  **Using the Generated Collection:**
    *   The collection will have folders for each of your API tags (usually based on app names or viewsets).
    *   Requests will be pre-filled with paths and HTTP methods.
    *   For `POST`/`PUT`/`PATCH` requests, Postman will often provide a sample JSON body based on your serializers. You'll need to fill in the actual data.
    *   For path parameters (like `<order_id>`), Postman will use placeholders (e.g., `:order_id`). You'll need to set these either in the request URL or using Postman variables.

    **Example: Creating a Product in Postman after import**
    *   Find the "products" folder (or similar) in the imported collection.
    *   Find the `POST /api/products/` request.
    *   Go to the "Body" tab, select "raw" and "JSON".
    *   Enter the product data:
        ```json
        {
          "name": "Super Gadget",
          "sku": "SG001",
          "description": "An amazing super gadget.",
          "price": "199.99"
        }
        ```
    *   Click "Send".

    **Example: Creating an Order**
    *   Find the `POST /api/orders/` request.
    *   Body (raw JSON):
        ```json
        {
          "customer_name": "Test Customer",
          "items": [
            {
              "product_id": 1, // Make sure product with ID 1 exists
              "quantity": 2
            }
          ]
        }
        ```

### Manual Creation (If you don't want to use schema generation)

If you prefer not to use schema generation, you can manually create a Postman collection:

1.  **Create a New Collection:** In Postman, click "New" -> "Collection". Give it a name (e.g., "Order Fulfillment API").
2.  **Add Requests:**
    *   For each API endpoint you defined:
        *   Click the three dots next to your collection name and "Add Request".
        *   Name the request descriptively (e.g., "Create Product", "List Orders").
        *   Set the HTTP method (GET, POST, PUT, DELETE).
        *   Enter the request URL (e.g., `http://127.0.0.1:8000/api/products/`).
        *   For POST/PUT, go to the "Body" tab, select "raw", choose "JSON", and paste an example payload.
        *   For GET requests with path parameters (e.g., `/api/orders/{id}/`), use Postman's path variable syntax: `/api/orders/:order_id/`. You can then define `order_id` in the "Params" tab or set it as a collection/environment variable.
3.  **Organize into Folders:** You can create folders within your collection to group related requests (e.g., "Products", "Orders").
4.  **Use Environment Variables:** For `base_url` (`http://127.0.0.1:8000`), product IDs, order IDs, etc., use Postman environment variables for easier management.
    *   Click the "eye" icon (Environment quick look) in the top-right, then "Add" to create a new environment (e.g., "Local Dev").
    *   Define variables like `{{baseUrl}} = http://127.0.0.1:8000`.
    *   Then, in your requests, use `{{baseUrl}}/api/products/`.

This manual process is more time-consuming but gives you full control. However, using `drf-spectacular` is highly recommended for DRF projects as it keeps your Postman collection in sync with your API as it evolves.


## Further Considerations / Potential Improvements
*   **Authentication & Authorization:** Secure API endpoints.
*   **Input Validation:** More robust validation for all inputs.
*   **Idempotency:** Ensure all Celery tasks are fully idempotent, especially if retries or re-queuing for stale orders are implemented more aggressively.
*   **Monitoring & Logging:** Integrate comprehensive logging (e.g., ELK stack) and monitoring (e.g., Prometheus, Grafana) for a true production system.
*   **Distributed Tracing:** For complex microservice-like interactions (though this is a monolith, good for debugging task chains).
*   **Payment Integration:** Placeholder for actual payment processing.
*   **Notifications:** Customer notifications at different order stages.
*   **Configuration Management:** Use environment variables more extensively (e.g., for Celery delays, stale thresholds).
*   **Testing:** Comprehensive unit and integration tests.