import logging
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class DataExtraction:
    """
    Utilidad para extracción determinista de datos desde el historial de chat.
    Actúa como un 'Guardrail' lógico antes de invocar al LLM.
    Adaptado para Colegios San Ángel (3 planteles).
    """

    # Regex Patterns
    PHONE_PATTERN = r'(?:\+?52)?\s*(?:[ .-]*\(?(\d{2,3})\)?[ .-]*(\d{3,4})[ .-]*(\d{4})|\b(\d{8,10})\b)'
    EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

    @staticmethod
    def _get_campus_keywords() -> dict:
        """Lazy-load campus keywords from the registry singleton."""
        try:
            from app.dependencies import campus_registry
            return campus_registry.get_keywords_map()
        except Exception:
            # Fallback for test/import-time scenarios
            return {
                'puebla': 'puebla', 'pue': 'puebla',
                'coatzacoalcos': 'coatzacoalcos', 'coatza': 'coatzacoalcos',
                'poza rica': 'pozarica', 'poza': 'pozarica',
            }

    @staticmethod
    def extract_phone(text: str) -> Optional[str]:
        """Extrae y normaliza un número de teléfono a 10 dígitos."""
        if not text: return None

        matches = re.finditer(DataExtraction.PHONE_PATTERN, text)
        for match in matches:
            groups = match.groups()
            full_num = "".join([g for g in groups if g])
            full_num = re.sub(r'\D', '', full_num)

            if 8 <= len(full_num) <= 10:
                logger.info("Teléfono extraído y validado: %s", full_num)
                return full_num
        return None

    @staticmethod
    def extract_email(text: str) -> Optional[str]:
        """Extrae el primer email válido encontrado."""
        match = re.search(DataExtraction.EMAIL_PATTERN, text)
        return match.group(0) if match else None

    @staticmethod
    def check_complete_data_in_history(history_msgs: List[Any], full_name_param: str = None) -> Dict[str, Any]:
        """
        Verifica si el historial contiene los 5 datos requeridos.
        Adapted: 'career' replaced with 'nivel educativo' keywords.
        """
        user_text = []
        for m in history_msgs:
            role = m.get('role') if isinstance(m, dict) else (
                'user' if m.type == 'human' else 'assistant'
            )
            content = m.get('content') if isinstance(m, dict) else m.content

            if role == 'user' and content:
                user_text.append(str(content).lower())

        full_text = " ".join(user_text)

        # 1. Campus (Plantel)
        detected_campus = None
        import re as _re
        for keyword, normalized in DataExtraction._get_campus_keywords().items():
            if _re.search(r'\b' + _re.escape(keyword) + r'\b', full_text):
                detected_campus = normalized
                break

        # 2. Nivel Educativo (replaces career keywords for K-12)
        level_keywords = [
            'preescolar', 'kinder', 'kínder', 'kindergarten',
            'primaria', 'elementary',
            'secundaria', 'middle',
            'bachillerato', 'preparatoria', 'prepa', 'high school',
        ]
        has_career = any(kw in full_text for kw in level_keywords)

        # 3. Nombre
        has_name = bool(full_name_param and len(full_name_param.strip().split()) >= 2)

        # 4. Teléfono
        phone = DataExtraction.extract_phone(full_text)

        # 5. Email
        email = DataExtraction.extract_email(full_text)

        return {
            'complete': all([detected_campus, has_career, has_name, phone, email]),
            'has_campus': bool(detected_campus),
            'detected_campus': detected_campus,
            'has_career': has_career,
            'has_name': has_name,
            'has_phone': bool(phone),
            'phone': phone,
            'has_email': bool(email),
            'email': email
        }
