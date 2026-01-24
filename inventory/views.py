from rest_framework import generics, status, permissions, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Sum, Avg, Count
from django.utils import timezone
from django.http import HttpResponse
from datetime import timedelta
from decimal import Decimal

from .models import (
    Category, Supplier, Product, ProductImage, StockMovement,
    ProductAlert, Barcode, ProductReview, Clearance
)
from .serializers import (
    CategorySerializer, SupplierSerializer, ProductListSerializer,
    ProductDetailSerializer, ProductCreateUpdateSerializer, StockMovementSerializer,
    ProductAlertSerializer, BarcodeSerializer, ProductReviewSerializer,
    BulkProductUpdateSerializer, ProductStatsSerializer, ProductImageSerializer,
    ClearanceSerializer
)
from .filters import ProductFilter
from .services import BarcodeService, TicketService, ProductService


class CategoryListCreateView(generics.ListCreateAPIView):
    """List and create categories"""
    
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    pagination_class = None  # Disable pagination for categories - return plain array
    
    def get_queryset(self):
        """Filter categories by current user"""
        return Category.objects.filter(
            created_by=self.request.user,
            is_active=True
        )
    
    def perform_create(self, serializer):
        """Set the created_by field to current user"""
        serializer.save(created_by=self.request.user)


class CategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, and delete categories"""
    
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter categories by current user"""
        return Category.objects.filter(created_by=self.request.user)


class SupplierListCreateView(generics.ListCreateAPIView):
    """List and create suppliers"""
    
    serializer_class = SupplierSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'contact_person', 'email']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    pagination_class = None  # Disable pagination for suppliers - return plain array
    
    def get_queryset(self):
        """Filter suppliers by current user"""
        return Supplier.objects.filter(
            created_by=self.request.user,
            is_active=True
        )
    
    def perform_create(self, serializer):
        """Set the created_by field to current user"""
        serializer.save(created_by=self.request.user)


class SupplierDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, and delete suppliers"""
    
    serializer_class = SupplierSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter suppliers by current user"""
        return Supplier.objects.filter(created_by=self.request.user)


class ProductListCreateView(generics.ListCreateAPIView):
    """List and create products"""
    
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'barcode', 'brand', 'description']
    ordering_fields = ['name', 'price', 'quantity', 'expiry_date', 'added_date']
    ordering = ['-added_date']
    
    def get_queryset(self):
        user = self.request.user
        from django.db.models import Q
        # Filter products by user's supermarkets (owner or staff)
        return Product.objects.filter(
            (Q(supermarket__owner=user) | Q(supermarket__staff__user=user)),
            is_active=True
        ).select_related('category', 'supplier', 'supermarket')
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ProductCreateUpdateSerializer
        return ProductListSerializer


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, and delete products"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        from django.db.models import Q
        return Product.objects.filter(
            (Q(supermarket__owner=user) | Q(supermarket__staff__user=user))
        ).select_related('category', 'supplier', 'supermarket', 'created_by')
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ProductCreateUpdateSerializer
        return ProductDetailSerializer


class ProductStockUpdateView(APIView):
    """Update product stock with movement tracking"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, product_id):
        try:
            from django.db.models import Q
            product = Product.objects.get(
                Q(id=product_id) & 
                (Q(supermarket__owner=request.user) | Q(supermarket__staff__user=request.user))
            )
        except (Product.DoesNotExist, ValueError):
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        movement_type = request.data.get('movement_type')
        quantity_change = request.data.get('quantity', 0)
        unit_cost = request.data.get('unit_cost')
        reference = request.data.get('reference', '')
        notes = request.data.get('notes', '')
        
        if not movement_type or quantity_change == 0:
            return Response(
                {'error': 'Movement type and quantity are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        previous_quantity = product.quantity
        
        # Calculate new quantity based on movement type
        if movement_type in ['IN', 'RETURNED']:
            new_quantity = previous_quantity + abs(quantity_change)
        elif movement_type in ['OUT', 'EXPIRED', 'DAMAGED']:
            new_quantity = max(0, previous_quantity - abs(quantity_change))
        elif movement_type == 'ADJUSTMENT':
            new_quantity = quantity_change  # Direct quantity set
        else:
            return Response(
                {'error': 'Invalid movement type'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update product quantity
        product.quantity = new_quantity
        product.save()
        
        # Create stock movement record
        total_cost = None
        if unit_cost:
            total_cost = Decimal(str(unit_cost)) * abs(quantity_change)
        
        StockMovement.objects.create(
            product=product,
            movement_type=movement_type,
            quantity=quantity_change if movement_type != 'ADJUSTMENT' else new_quantity - previous_quantity,
            previous_quantity=previous_quantity,
            new_quantity=new_quantity,
            unit_cost=unit_cost,
            total_cost=total_cost,
            reference=reference,
            notes=notes,
            created_by=request.user
        )
        
        # Check for alerts
        self.check_and_create_alerts(product)
        
        return Response({
            'message': 'Stock updated successfully',
            'previous_quantity': previous_quantity,
            'new_quantity': new_quantity,
            'product': ProductListSerializer(product).data
        })
    
    def check_and_create_alerts(self, product):
        """Check and create alerts for the product"""
        alerts_to_create = []
        
        # Low stock alert
        if product.is_low_stock and product.quantity > 0:
            alerts_to_create.append(ProductAlert(
                product=product,
                alert_type='LOW_STOCK',
                priority='MEDIUM',
                message=f'{product.name} is running low on stock. Current quantity: {product.quantity}'
            ))
        
        # Out of stock alert
        if product.quantity == 0:
            alerts_to_create.append(ProductAlert(
                product=product,
                alert_type='OUT_OF_STOCK',
                priority='HIGH',
                message=f'{product.name} is out of stock.'
            ))
        
        # Expiry alerts
        if product.is_expiring_soon:
            alerts_to_create.append(ProductAlert(
                product=product,
                alert_type='EXPIRING_SOON',
                priority='MEDIUM',
                message=f'{product.name} expires in {product.days_until_expiry} days.'
            ))
        elif product.is_expired:
            alerts_to_create.append(ProductAlert(
                product=product,
                alert_type='EXPIRED',
                priority='CRITICAL',
                message=f'{product.name} has expired.'
            ))
        
        # Bulk create alerts (avoiding duplicates)
        for alert in alerts_to_create:
            if not ProductAlert.objects.filter(
                product=product,
                alert_type=alert.alert_type,
                is_resolved=False
            ).exists():
                alert.save()


class BulkProductUpdateView(APIView):
    """Bulk update products"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = BulkProductUpdateSerializer(data=request.data)
        if serializer.is_valid():
            product_ids = serializer.validated_data['product_ids']
            updates = serializer.validated_data['updates']
            
            # Filter products by user's supermarkets
            products = Product.objects.filter(
                id__in=product_ids,
                supermarket__owner=request.user
            )
            
            if not products.exists():
                return Response(
                    {'error': 'No products found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update products
            updated_count = products.update(**updates)
            
            return Response({
                'message': f'{updated_count} products updated successfully',
                'updated_count': updated_count
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProductStatsView(APIView):
    """Get product statistics"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        from django.db.models import Q
        products = Product.objects.filter(
            (Q(supermarket__owner=user) | Q(supermarket__staff__user=user)),
            is_active=True
        )
        
        # Calculate statistics
        total_products = products.count()
        total_value = products.aggregate(
            total=Sum('quantity') * Sum('price')
        )['total'] or 0
        
        low_stock_count = products.filter(
            quantity__lte=models.F('min_stock_level')
        ).count()
        
        expired_count = products.filter(
            expiry_date__lt=timezone.now().date()
        ).count()
        
        expiring_soon_count = products.filter(
            expiry_date__lte=timezone.now().date() + timedelta(days=7),
            expiry_date__gt=timezone.now().date()
        ).count()
        
        out_of_stock_count = products.filter(quantity=0).count()
        
        categories_count = Category.objects.filter(
            created_by=user,
            product__in=products
        ).distinct().count()
        
        suppliers_count = Supplier.objects.filter(
            created_by=user,
            product__in=products
        ).distinct().count()
        
        # Calculate average profit margin
        profit_margins = []
        for product in products.filter(cost_price__gt=0):
            if product.selling_price > product.cost_price:
                margin = ((product.selling_price - product.cost_price) / product.cost_price) * 100
                profit_margins.append(margin)
        
        average_profit_margin = sum(profit_margins) / len(profit_margins) if profit_margins else 0
        
        stats = {
            'total_products': total_products,
            'total_value': total_value,
            'low_stock_count': low_stock_count,
            'expired_count': expired_count,
            'expiring_soon_count': expiring_soon_count,
            'out_of_stock_count': out_of_stock_count,
            'categories_count': categories_count,
            'suppliers_count': suppliers_count,
            'average_profit_margin': round(average_profit_margin, 2)
        }
        
        serializer = ProductStatsSerializer(stats)
        return Response(serializer.data)


class StockMovementListView(generics.ListAPIView):
    """List stock movements"""
    
    serializer_class = StockMovementSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['movement_type', 'product']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        user = self.request.user


class ClearanceListCreateView(generics.ListCreateAPIView):
    """List and create clearance deals (scoped to current user's supermarkets)."""

    serializer_class = ClearanceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering = ['-created_at']
    pagination_class = None  # match frontend expectations (plain array)

    def get_queryset(self):
        user = self.request.user
        return Clearance.objects.filter(product__supermarket__owner=user).select_related('product')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ClearanceDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ClearanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Clearance.objects.filter(product__supermarket__owner=user)


class ClearanceActiveListView(generics.ListAPIView):
    serializer_class = ClearanceSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        qs = Clearance.objects.filter(product__supermarket__owner=user)
        return [c for c in qs if c.is_active]


class ClearanceBarcodeView(APIView):
    """Return a barcode image for the clearance-generated barcode."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, clearance_id):
        try:
            from django.core.exceptions import ValidationError
            from django.db.models import Q
            import uuid
            
            print(f"DEBUG: ClearanceBarcodeView.get called with clearance_id: {clearance_id}")

            # Validate UUID format explicitly
            try:
                uuid_obj = uuid.UUID(str(clearance_id))
            except (ValueError, TypeError):
                print(f"DEBUG: Invalid UUID format provided for clearance barcode: {clearance_id}")
                return Response({'error': f'Invalid clearance ID format: {clearance_id}'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                clearance = Clearance.objects.get(
                    Q(id=clearance_id) & 
                    (Q(product__supermarket__owner=request.user) | Q(product__supermarket__staff__user=request.user))
                )
            except (Clearance.DoesNotExist, ValidationError, ValueError):
                if Clearance.objects.filter(id=clearance_id).exists():
                    print(f"DEBUG: Clearance {clearance_id} exists but permission denied for user {request.user}")
                    return Response({'error': 'Permission denied to access this clearance barcode'}, status=status.HTTP_403_FORBIDDEN)
                else:
                    print(f"DEBUG: Clearance not found in database: {clearance_id}")
                    return Response({'error': f'Clearance record not found: {clearance_id}'}, status=status.HTTP_404_NOT_FOUND)

            if not clearance.generated_barcode:
                # Force generation if missing
                clearance.save()
            
            try:
                img_bytes = BarcodeService.generate_barcode_image(clearance.generated_barcode)
                return HttpResponse(img_bytes, content_type='image/png')
            except Exception as e:
                print(f"DEBUG: Clearance barcode generation failed: {str(e)}")
                return Response({'error': f'Failed to generate barcode image: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            print(f"DEBUG: Unexpected error in ClearanceBarcodeView: {str(e)}")
            return Response({'error': f'Error generating clearance barcode: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClearanceTicketView(APIView):
    """Return a PDF ticket that includes clearance info and barcode."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, clearance_id):
        try:
            from django.core.exceptions import ValidationError
            from django.db.models import Q
            import uuid
            
            print(f"DEBUG: ClearanceTicketView.get called with clearance_id: {clearance_id}")

            # Validate UUID format explicitly
            try:
                uuid_obj = uuid.UUID(str(clearance_id))
            except (ValueError, TypeError):
                print(f"DEBUG: Invalid UUID format provided for clearance ticket: {clearance_id}")
                return Response({'error': f'Invalid clearance ID format: {clearance_id}'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                clearance = Clearance.objects.get(
                    Q(id=clearance_id) & 
                    (Q(product__supermarket__owner=request.user) | Q(product__supermarket__staff__user=request.user))
                )
            except (Clearance.DoesNotExist, ValidationError, ValueError):
                if Clearance.objects.filter(id=clearance_id).exists():
                    print(f"DEBUG: Clearance {clearance_id} exists but permission denied for user {request.user}")
                    return Response({'error': 'Permission denied to access this clearance ticket'}, status=status.HTTP_403_FORBIDDEN)
                else:
                    print(f"DEBUG: Clearance not found in database for ticket: {clearance_id}")
                    return Response({'error': f'Clearance record not found: {clearance_id}'}, status=status.HTTP_404_NOT_FOUND)

            # Create a lightweight Product-like wrapper to reuse TicketService
            # but override barcode/price/name where relevant
            product = clearance.product
            original_barcode = getattr(product, 'barcode', '')

            # Render ticket with clearance details at top using ReportLab similar to TicketService
            # For simplicity, reuse TicketService to generate base ticket, then just change barcode
            try:
                # Temporarily swap barcode for generation
                setattr(product, 'barcode', clearance.generated_barcode or original_barcode)
                pdf_bytes = TicketService.generate_product_ticket(product, include_qr=False)
                # Restore
                setattr(product, 'barcode', original_barcode)
                return HttpResponse(pdf_bytes, content_type='application/pdf')
            except Exception as e:
                # Restore and return error
                setattr(product, 'barcode', original_barcode)
                print(f"DEBUG: Clearance ticket generation failed: {str(e)}")
                return Response({'error': f'Failed to generate ticket PDF: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            print(f"DEBUG: Unexpected error in ClearanceTicketView: {str(e)}")
            return Response({'error': f'Error generating clearance ticket: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return StockMovement.objects.filter(
            product__supermarket__owner=user
        ).select_related('product', 'created_by')


class ProductAlertListView(generics.ListAPIView):
    """List product alerts"""
    
    serializer_class = ProductAlertSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['alert_type', 'priority', 'is_read', 'is_resolved']
    ordering_fields = ['created_at', 'priority']
    ordering = ['-created_at']
    
    def get_queryset(self):
        user = self.request.user
        return ProductAlert.objects.filter(
            product__supermarket__owner=user
        ).select_related('product', 'resolved_by')


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_alert_as_read(request, alert_id):
    """Mark alert as read"""
    try:
        alert = ProductAlert.objects.get(
            id=alert_id,
            product__supermarket__owner=request.user
        )
        alert.is_read = True
        alert.save()
        
        return Response({'message': 'Alert marked as read'})
    except ProductAlert.DoesNotExist:
        return Response(
            {'error': 'Alert not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def resolve_alert(request, alert_id):
    """Resolve alert"""
    try:
        alert = ProductAlert.objects.get(
            id=alert_id,
            product__supermarket__owner=request.user
        )
        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.resolved_by = request.user
        alert.save()
        
        return Response({'message': 'Alert resolved'})
    except ProductAlert.DoesNotExist:
        return Response(
            {'error': 'Alert not found'},
            status=status.HTTP_404_NOT_FOUND
        )


class ProductReviewListCreateView(generics.ListCreateAPIView):
    """List and create product reviews"""
    
    serializer_class = ProductReviewSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['product', 'rating']
    ordering_fields = ['created_at', 'rating']
    ordering = ['-created_at']
    
    def get_queryset(self):
        user = self.request.user
        return ProductReview.objects.filter(
            product__supermarket__owner=user
        ).select_related('product', 'user')


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def search_products_by_barcode(request, barcode):
    """Search products by barcode"""
    try:
        product = Product.objects.get(
            barcode=barcode,
            supermarket__owner=request.user,
            is_active=True
        )
        serializer = ProductDetailSerializer(product)
        return Response(serializer.data)
    except Product.DoesNotExist:
        return Response(
            {'error': 'Product not found'},
            status=status.HTTP_404_NOT_FOUND
        )


class BarcodeGenerationView(APIView):
    """Generate barcode for a product"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, product_id):
        """Get barcode image for a product"""
        try:
            from django.core.exceptions import ValidationError
            from django.db.models import Q
            import uuid
            
            print(f"DEBUG: BarcodeGenerationView.get called with product_id: {product_id}")

            # Validate UUID format explicitly to avoid internal server errors or misleading 404s
            try:
                if isinstance(product_id, str) and not product_id.replace('-', '').isalnum():
                    # Quick check for obviously non-UUID strings
                    pass 
                uuid_obj = uuid.UUID(str(product_id))
            except (ValueError, TypeError):
                print(f"DEBUG: Invalid UUID format provided: {product_id}")
                return Response({'error': f'Invalid product ID format: {product_id}'}, status=status.HTTP_400_BAD_REQUEST)

            # Try to find the product with permissions
            try:
                product = Product.objects.get(
                    Q(id=product_id) & 
                    (Q(supermarket__owner=request.user) | Q(supermarket__staff__user=request.user))
                )
            except (Product.DoesNotExist, ValidationError, ValueError):
                # Try checking if it exists at all to give a better error message
                if Product.objects.filter(id=product_id).exists():
                    print(f"DEBUG: Product {product_id} exists but permission denied for user {request.user}")
                    return Response({'error': 'Permission denied to access this product barcode'}, status=status.HTTP_403_FORBIDDEN)
                else:
                    print(f"DEBUG: Product not found in database: {product_id}")
                    return Response({'error': f'Product not found: {product_id}'}, status=status.HTTP_404_NOT_FOUND)

            # Generate barcode if not exists
            if not product.barcode:
                product.barcode = BarcodeService.generate_barcode_number(str(product.id))
                product.save()
            
            barcode_type = request.GET.get('type', 'CODE128')
            format_type = request.GET.get('format', 'PNG')
            
            # Generate barcode image
            try:
                barcode_image = BarcodeService.generate_barcode_image(
                    product.barcode, 
                    barcode_type, 
                    format_type
                )
            except Exception as e:
                print(f"DEBUG: Barcode image generation failed: {str(e)}")
                return Response(
                    {'error': f'Failed to generate barcode image: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            response = HttpResponse(barcode_image, content_type=f'image/{format_type.lower()}')
            response['Content-Disposition'] = f'attachment; filename="{product.name}_barcode.{format_type.lower()}"'
            return response
            
        except Exception as e:
            print(f"DEBUG: Unexpected error in BarcodeGenerationView: {str(e)}")
            return Response(
                {'error': f'Error generating barcode: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def post(self, request, product_id):
        """Generate and save barcode for a product"""
        try:
            from django.core.exceptions import ValidationError
            from django.db.models import Q
            
            print(f"DEBUG: BarcodeGenerationView.post called with product_id: {product_id}")

            try:
                product = Product.objects.get(
                    Q(id=product_id) & 
                    (Q(supermarket__owner=request.user) | Q(supermarket__staff__user=request.user))
                )
            except (Product.DoesNotExist, ValidationError, ValueError):
                if Product.objects.filter(id=product_id).exists():
                    print(f"DEBUG: Product {product_id} exists but permission denied for user {request.user}")
                    return Response({'error': 'Permission denied to access this product'}, status=status.HTTP_403_FORBIDDEN)
                else:
                    print(f"DEBUG: Product not found: {product_id}")
                    return Response({'error': f'Product not found: {product_id}'}, status=status.HTTP_404_NOT_FOUND)
            
            barcode_type = request.data.get('barcode_type', 'CODE128')
            
            # Create barcode record
            barcode_obj = BarcodeService.create_product_barcode(product, barcode_type)
            
            serializer = BarcodeSerializer(barcode_obj)
            return Response(serializer.data)
            
        except Exception as e:
            print(f"DEBUG: Unexpected error in BarcodeGenerationView.post: {str(e)}")
            return Response(
                {'error': f'Error creating barcode: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ProductTicketView(APIView):
    """Generate product ticket/label"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, product_id):
        """Generate single product ticket as PDF"""
        try:
            from django.core.exceptions import ValidationError
            from django.db.models import Q
            import uuid
            
            print(f"DEBUG: ProductTicketView.get called with product_id: {product_id}")

            # Validate UUID format explicitly
            try:
                uuid_obj = uuid.UUID(str(product_id))
            except (ValueError, TypeError):
                print(f"DEBUG: Invalid UUID format provided for ticket: {product_id}")
                return Response({'error': f'Invalid product ID format: {product_id}'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                product = Product.objects.get(
                    Q(id=product_id) & 
                    (Q(supermarket__owner=request.user) | Q(supermarket__staff__user=request.user))
                )
            except (Product.DoesNotExist, ValidationError, ValueError):
                if Product.objects.filter(id=product_id).exists():
                    print(f"DEBUG: Product {product_id} exists but permission denied for user {request.user}")
                    return Response({'error': 'Permission denied to access this product ticket'}, status=status.HTTP_403_FORBIDDEN)
                else:
                    print(f"DEBUG: Product not found in database for ticket: {product_id}")
                    return Response({'error': f'Product not found: {product_id}'}, status=status.HTTP_404_NOT_FOUND)
            
            include_qr = request.GET.get('include_qr', 'true').lower() == 'true'
            
            # Generate ticket PDF
            ticket_pdf = TicketService.generate_product_ticket(product, include_qr)
            
            response = HttpResponse(ticket_pdf, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{product.name}_ticket.pdf"'
            return response
            
        except Exception as e:
            print(f"DEBUG: Unexpected error in ProductTicketView: {str(e)}")
            return Response(
                {'error': f'Error generating ticket: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class BulkTicketsView(APIView):
    """Generate bulk tickets for multiple products"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Generate tickets for multiple products"""
        try:
            product_ids = request.data.get('product_ids', [])
            tickets_per_page = request.data.get('tickets_per_page', 8)
            
            if not product_ids:
                return Response(
                    {'error': 'No product IDs provided'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get products
            from django.db.models import Q
            import uuid
            
            # Filter and validate product IDs
            valid_product_ids = []
            for pid in product_ids:
                try:
                    uuid.UUID(str(pid))
                    valid_product_ids.append(pid)
                except (ValueError, TypeError):
                    print(f"DEBUG: Skipping invalid UUID in bulk tickets: {pid}")
            
            if not valid_product_ids:
                return Response(
                    {'error': 'No valid product IDs provided'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            products = Product.objects.filter(
                Q(id__in=valid_product_ids) & 
                (Q(supermarket__owner=request.user) | Q(supermarket__staff__user=request.user)),
                is_active=True
            )
            
            if not products.exists():
                return Response(
                    {'error': 'No products found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Generate bulk tickets PDF
            tickets_pdf = TicketService.generate_bulk_tickets(
                list(products), 
                tickets_per_page
            )
            
            response = HttpResponse(tickets_pdf, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="product_tickets.pdf"'
            return response
            
        except Exception as e:
            return Response(
                {'error': f'Error generating tickets: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class BulkBarcodesView(APIView):
    """Generate bulk barcodes sheet"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Generate barcode sheet for multiple products"""
        try:
            product_ids = request.data.get('product_ids', [])
            barcodes_per_page = request.data.get('barcodes_per_page', 20)
            
            from django.db.models import Q
            import uuid
            
            if not product_ids:
                # If no specific products, get all products for the user
                products = Product.objects.filter(
                    (Q(supermarket__owner=request.user) | Q(supermarket__staff__user=request.user)),
                    is_active=True
                )
            else:
                # Filter and validate product IDs
                valid_product_ids = []
                for pid in product_ids:
                    try:
                        uuid.UUID(str(pid))
                        valid_product_ids.append(pid)
                    except (ValueError, TypeError):
                        print(f"DEBUG: Skipping invalid UUID in bulk barcodes: {pid}")
                
                if not valid_product_ids:
                    return Response(
                        {'error': 'No valid product IDs provided'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                products = Product.objects.filter(
                    Q(id__in=valid_product_ids) & 
                    (Q(supermarket__owner=request.user) | Q(supermarket__staff__user=request.user)),
                    is_active=True
                )
            
            if not products.exists():
                return Response(
                    {'error': 'No products found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Generate barcode sheet PDF
            barcode_pdf = TicketService.generate_barcode_sheet(
                list(products), 
                barcodes_per_page
            )
            
            response = HttpResponse(barcode_pdf, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="product_barcodes.pdf"'
            return response
            
        except Exception as e:
            return Response(
                {'error': f'Error generating barcode sheet: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def generate_barcode_for_product(request, product_id):
    """Generate a new barcode for an existing product"""
    try:
        from django.core.exceptions import ValidationError
        from django.db.models import Q
        import uuid
        
        print(f"DEBUG: generate_barcode_for_product called with product_id: {product_id}")

        # Validate UUID format explicitly
        try:
            uuid_obj = uuid.UUID(str(product_id))
        except (ValueError, TypeError):
            print(f"DEBUG: Invalid UUID format provided for regeneration: {product_id}")
            return Response({'error': f'Invalid product ID format: {product_id}'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            product = Product.objects.get(
                Q(id=product_id) & 
                (Q(supermarket__owner=request.user) | Q(supermarket__staff__user=request.user))
            )
        except (Product.DoesNotExist, ValidationError, ValueError):
            if Product.objects.filter(id=product_id).exists():
                print(f"DEBUG: Product {product_id} exists but permission denied for user {request.user}")
                return Response({'error': 'Permission denied to access this product'}, status=status.HTTP_403_FORBIDDEN)
            else:
                print(f"DEBUG: Product not found in database for regeneration: {product_id}")
                return Response({'error': f'Product not found: {product_id}'}, status=status.HTTP_404_NOT_FOUND)
        
        # Generate new barcode
        new_barcode = BarcodeService.generate_barcode_number(str(product.id))
        product.barcode = new_barcode
        product.save()
        
        # Create barcode record
        barcode_obj = BarcodeService.create_product_barcode(product)
        
        return Response({
            'message': 'Barcode generated successfully',
            'barcode': new_barcode,
            'product': ProductListSerializer(product).data
        })
        
    except Exception as e:
        print(f"DEBUG: Unexpected error in generate_barcode_for_product: {str(e)}")
        return Response(
            {'error': f'Error generating barcode: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )