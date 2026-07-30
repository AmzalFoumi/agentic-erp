"""HTTP routes, one module per resource.

Each module exports an `APIRouter` that main.py includes. The split is by
resource rather than by verb, matching services/ one-to-one: products.py here
adapts services/products.py and nothing else.
"""
