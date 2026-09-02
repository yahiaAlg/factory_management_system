# core/signals.py
"""
Signals for the core application.

Registered signals:
  1. post_delete on PieceJointe (generic document-proof model, mirrors the
     avicole project) → delete the underlying file from storage whenever a
     PieceJointe row is removed, whether directly or via cascade when its
     owning record (SupplierDN, SupplierInvoice, Expense, ClientDN, ...) is
     deleted.
"""

import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from core.models import PieceJointe

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=PieceJointe)
def supprimer_fichier_piece_jointe(sender, instance, **kwargs):
    """
    PieceJointe rows are removed automatically whenever their owning record
    is deleted (GenericRelation participates in the delete collector like a
    CASCADE FK), but Django never deletes the underlying file from storage
    on model delete. Without this, every removed DN/invoice/expense/...
    would leave an orphaned file behind. This also fires for direct/manual
    PieceJointe deletion (e.g. from the admin or the "remove attachment"
    view action).
    """
    if instance.fichier:
        instance.fichier.delete(save=False)
