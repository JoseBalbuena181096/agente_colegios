"""
SafetyNetService: Deterministic bypass logic that skips the LLM when possible.
Adapted for Colegios San Ángel (Luca 🐻).
"""

import logging
from app.utils.data_extraction import DataExtraction
from app.services.loop_detector import LoopDetector

logger = logging.getLogger(__name__)


# --- KEYWORDS ---

HUMAN_KEYWORDS = ["asesor", "humano", "persona", "alguien", "agendar", "cita"]

ADMIN_KEYWORDS = [
    "boleta", "kardex", "servicio social",
    "baja temporal", "baja definitiva", "reinscripción", "reinscripcion",
    "certificado", "constancia", "credencial",
    "cambio de escuela", "equivalencia", "revalidación", "revalidacion",
    "historial académico", "historial academico",
    "pago de colegiatura", "factura", "estado de cuenta",
    "plataforma", "moodle", "contraseña", "password",
]


def check_human_request(message: str) -> bool:
    """Returns True if user explicitly asks for a human agent."""
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in HUMAN_KEYWORDS) and len(msg_lower) < 50


def check_admin_topic(message: str) -> str | None:
    """Returns an admin handoff message if the message is about admin topics."""
    msg_lower = message.lower()
    for kw in ADMIN_KEYWORDS:
        if kw in msg_lower:
            return (
                f"¡Hola! Veo que tu consulta es sobre un trámite académico/administrativo ({kw}). "
                f"Este canal es exclusivo para nuevos alumnos y admisiones. "
                f"Para trámites de alumnos actuales, por favor contacta a tu plantel directamente. "
                f"¡Éxito! 📚"
            )
    return None


def check_complete_data(message: str, lead_form_data: dict | None = None) -> tuple[str | None, str | None]:
    """Check if the message contains both phone and email (complete data)."""
    incoming_phone = DataExtraction.extract_phone(message)
    incoming_email = DataExtraction.extract_email(message)

    if not incoming_phone and lead_form_data and lead_form_data.get('phone'):
        incoming_phone = lead_form_data['phone']
        clean = ''.join(filter(str.isdigit, incoming_phone))
        if len(clean) >= 10:
            incoming_phone = clean[-10:]
        logger.info("Teléfono obtenido del Lead Form parseado: %s", incoming_phone)

    if not incoming_email and lead_form_data and lead_form_data.get('email'):
        incoming_email = lead_form_data['email']
        logger.info("Email obtenido del Lead Form parseado: %s", incoming_email)

    if incoming_phone and incoming_email:
        return incoming_phone, incoming_email

    return None, None


def check_booking_sent(history: list) -> bool:
    """Check if a booking link was already sent in the conversation history."""
    booking_link_url = "link.superleads.mx/widget/booking"
    for msg in history:
        content = msg.get('content', '')
        if msg['role'] == 'assistant' and booking_link_url in content:
            return True
    return False


def check_booking_sent_with_state(history: list, lead_state_service=None, contact_id: str = None) -> dict:
    """Enhanced booking-sent check with post-booking tracking."""
    if lead_state_service and contact_id:
        booking_state = lead_state_service.get_booking_state(contact_id)
        if booking_state["sent"]:
            return booking_state

    sent = check_booking_sent(history)
    if sent:
        if lead_state_service and contact_id:
            lead_state_service.set_booking_sent(contact_id)
        return {"sent": True, "post_booking_count": 0}

    return {"sent": False, "post_booking_count": 0}


def check_loop(history: list, proposed_response: str) -> bool:
    """Check if the proposed response would create a loop."""
    return LoopDetector.detect_loop(history, proposed_response)


def is_greeting_loop(response_text: str) -> bool:
    """Check if the response is stuck in a greeting loop."""
    return "Soy Luca" in response_text or "inscribir" in response_text
