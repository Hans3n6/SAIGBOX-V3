"""
CRM Providers Package
Contains adapters for various CRM systems
"""

from .base import CRMProvider, CRMContact, CRMDeal
from .hubspot_provider import HubSpotProvider

__all__ = ["CRMProvider", "CRMContact", "CRMDeal", "HubSpotProvider"]
