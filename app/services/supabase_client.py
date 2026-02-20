"""
Singleton Supabase client.
All services share this single instance instead of creating their own.
"""

import os
import logging
from supabase import create_client, Client
from typing import Optional

logger = logging.getLogger(__name__)

_client: Optional[Client] = None


def get_supabase() -> Optional[Client]:
    """Returns the shared Supabase client, creating it on first call."""
    global _client
    if _client is not None:
        return _client

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_TOKEN")

    if not supabase_url or not supabase_key:
        logger.warning("SUPABASE_URL or SUPABASE_TOKEN not found in env")
        return None

    _client = create_client(supabase_url, supabase_key)
    return _client
