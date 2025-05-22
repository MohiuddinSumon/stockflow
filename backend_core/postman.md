## Part 2: Generating a Postman Collection

The best way to get a Postman collection for a Django REST Framework API is by generating an OpenAPI (formerly Swagger) schema and then importing that into Postman. `drf-spectacular` is an excellent package for this.

1.  **Install `drf-spectacular`:**
    ```bash
    pip install drf-spectacular
    ```
    Add `drf-spectacular` to your `requirements.txt`.

2.  **Add `drf_spectacular` to `INSTALLED_APPS` in `backend_core/settings.py`:**
    ```python
    INSTALLED_APPS = [
        # ... other apps
        'rest_framework',
        'drf_spectacular', # Add this
        'products',
        'orders',
        # ...
    ]
    ```

3.  **Add `drf-spectacular` URLs to your main `backend_core/urls.py`:**
    ```python
    from django.contrib import admin
    from django.urls import path, include
    from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

    urlpatterns = [
        path('admin/', admin.site.urls),
        path('api/', include('products.urls')),
        path('api/', include('orders.urls')),

        # OpenAPI 3 schema:
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
        # Optional UI:
        path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
        path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    ]
    ```

4.  **(Optional but Recommended) Configure `drf-spectacular` in `settings.py`:**
    You can add default settings for your API documentation.
    ```python
    # backend_core/settings.py
    SPECTACULAR_SETTINGS = {
        'TITLE': 'Order Fulfillment System API',
        'DESCRIPTION': 'API for managing products, inventory, and a distributed order fulfillment workflow.',
        'VERSION': '1.0.0',
        'SERVE_INCLUDE_SCHEMA': False, # Usually False for security; schema served by SpectacularAPIView
        # OTHER SETTINGS
    }
    ```

5.  **Run the development server:**
    ```bash
    python manage.py runserver
    ```

6.  **Access the Schema or UI:**
    *   **Schema URL:** `http://127.0.0.1:8000/api/schema/` (this will download a `schema.yml` or display JSON depending on your browser/Accept headers). You can also use `?format=openapi-json` for JSON.
    *   **Swagger UI:** `http://127.0.0.1:8000/api/schema/swagger-ui/`
    *   **ReDoc UI:** `http://127.0.0.1:8000/api/schema/redoc/`

7.  **Import into Postman:**
    *   Open Postman.
    *   Click on "Import" (usually in the top-left).
    *   Go to the "Link" tab.
    *   Paste the schema URL: `http://127.0.0.1:8000/api/schema/` (or `http://127.0.0.1:8000/api/schema/?format=openapi-json` if Postman prefers JSON directly, though it usually handles YAML fine from a URL).
        Alternatively, you can download the `schema.yml` file from `http://127.0.0.1:8000/api/schema/` and then use the "File" tab in Postman's import dialog to upload it.
    *   Click "Continue" and follow the prompts. Postman will generate a collection based on your API schema.

    ![Postman Import Link](https://learning.postman.com/docs/getting-started/importing-data/importing-data-gifs/import-from-link.gif)
    *(This GIF shows the general idea of importing via link)*

8.  **Using the Generated Collection:**
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

---

Remember to update your `README.md` to include instructions on generating/importing the Postman collection and any relevant information about using environment variables if you set them up in Postman.