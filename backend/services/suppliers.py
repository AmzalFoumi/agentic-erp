"""Suppliers - who we buy from. NOT YET IMPLEMENTED.

A supplier is the counterparty on a purchase order: name, contact details,
payment terms, and lead time in days. Lead time is the field that earns its
keep - it is what turns "we are low on rice" into "order rice by Thursday".

TODO (after slice 1 is proven end to end):
  - core/models.py: a Supplier model, and a link table for which suppliers
    stock which products at what price (the same product often has two)
  - list_suppliers / get_supplier / create_supplier / update_supplier,
    mirroring the shape established in products.py
"""
