#!/usr/bin/env python
"""
Check if a specific product exists and debug permissions
"""

import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ims_backend.settings')
django.setup()

from inventory.models import Product
from accounts.models import User
from supermarkets.models import Supermarket

def check_product(product_id):
    """Check if product exists and show details"""
    print(f"Checking product: {product_id}")

    try:
        product = Product.objects.get(id=product_id)
        print(f"✅ Product found: {product.name}")
        print(f"   ID: {product.id}")
        print(f"   Barcode: {product.barcode}")
        print(f"   Supermarket: {product.supermarket}")
        print(f"   Supermarket Owner: {product.supermarket.owner}")
        print(f"   Supermarket Staff: {list(product.supermarket.staff.all())}")
        print(f"   Created by: {product.created_by}")
        print(f"   Is active: {product.is_active}")

        # Check all users
        print("\nAll users in system:")
        for user in User.objects.all():
            print(f"  - {user.email} (ID: {user.id})")

        return product

    except Product.DoesNotExist:
        print(f"❌ Product with ID {product_id} does not exist")

        print("\nExisting products:")
        for p in Product.objects.all()[:10]:  # Show first 10
            print(f"  - {p.id}: {p.name}")

        return None

if __name__ == '__main__':
    if len(sys.argv) > 1:
        product_id = sys.argv[1]
    else:
        product_id = 'c2e4e6f4-47ff-4c65-a558-f54c47d976e0'  # From the error

    check_product(product_id)
