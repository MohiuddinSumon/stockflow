from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Inventory, Product
from .serializers import InventorySerializer, ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

class InventoryViewSet(viewsets.ModelViewSet):
    queryset = Inventory.objects.select_related('product').all()
    serializer_class = InventorySerializer

    # Custom action to update stock for a product (might be simpler than full PUT/PATCH)
    @action(detail=True, methods=['post'], url_path='update-stock')
    def update_stock(self, request, pk=None):
        inventory_item = self.get_object()
        new_stock_level = request.data.get('stock_level')

        if new_stock_level is None:
            return Response({'error': 'stock_level is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            new_stock_level = int(new_stock_level)
            if new_stock_level < 0:
                raise ValueError("Stock level cannot be negative.")
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        inventory_item.stock_level = new_stock_level
        inventory_item.save()
        return Response(InventorySerializer(inventory_item).data)