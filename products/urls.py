from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import InventoryViewSet, ProductViewSet

router = DefaultRouter()
router.register(r'products', ProductViewSet)
router.register(r'inventory', InventoryViewSet)

urlpatterns = [
    path('', include(router.urls)),
]