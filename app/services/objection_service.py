"""
ObjectionService: Cache y matching de objeciones desde la tabla objection_playbook.
Carga las objeciones en memoria al iniciar y las matchea contra mensajes del usuario.
"""

import logging
from typing import Optional
from app.services.supabase_client import get_supabase

logger = logging.getLogger(__name__)


class ObjectionService:

    def __init__(self):
        self.client = get_supabase()

        # Cache en memoria
        self._cache: list[dict] = []
        self._load_cache()

    def _load_cache(self):
        """Carga las objeciones activas de Supabase en memoria."""
        if not self.client:
            logger.warning("ObjectionService: Sin cliente Supabase, usando cache vacío")
            return

        try:
            response = self.client.table("objection_playbook") \
                .select("*") \
                .eq("is_active", True) \
                .order("priority", desc=True) \
                .execute()

            self._cache = response.data or []
            logger.info("ObjectionService: %s objeciones cargadas en cache", len(self._cache))

        except Exception as e:
            logger.error("Error cargando objection_playbook: %s", e)
            self._cache = []

    def refresh_cache(self):
        """Recarga las objeciones desde Supabase."""
        self._load_cache()

    def match_objection(self, message: str) -> Optional[dict]:
        """
        Busca match de keywords en el mensaje del usuario.
        Retorna la objeción con mayor prioridad que haga match, o None.

        Returns:
            dict con {category, response_template, redirect_to_booking} o None
        """
        if not self._cache:
            return None

        msg_lower = message.lower()

        for objection in self._cache:
            keywords = objection.get("trigger_keywords", [])
            for keyword in keywords:
                if keyword.lower() in msg_lower:
                    return {
                        "category": objection["category"],
                        "response_template": objection["response_template"],
                        "redirect_to_booking": objection.get("redirect_to_booking", True),
                    }
        return None

    def get_all_active(self) -> list[dict]:
        """Retorna todas las objeciones activas (para inyectar en prompt)."""
        return self._cache

    def get_categories_summary(self) -> str:
        """
        Retorna un resumen de categorías disponibles para inyectar en el system prompt.
        Formato: lista de categorías con keywords principales.
        """
        if not self._cache:
            return ""

        categories = {}
        for obj in self._cache:
            cat = obj.get("category", "")
            if cat not in categories:
                keywords = obj.get("trigger_keywords", [])
                # Tomar las primeras 3 keywords como ejemplo
                sample = ", ".join(keywords[:3]) if keywords else ""
                categories[cat] = sample

        lines = []
        for cat, sample in categories.items():
            lines.append(f"- {cat}: ({sample})")

        return "\n".join(lines)
