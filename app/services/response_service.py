"""
ResponseService: Handles sending responses to GHL, booking link injection,
tag management, and Supabase persistence.
Adapted for Colegios San Ángel.
"""

import logging
import re
from app.utils.data_extraction import DataExtraction
from app.utils.helpers import detect_channel

logger = logging.getLogger(__name__)


# ===================================================================
#  PRE-SEND VALIDATION
# ===================================================================

_SYSTEM_LEAK_PATTERNS = [
    "[SISTEMA", "[SYSTEM", "DATO PRE-CAPTURADO",
    "[INTERNAL", "[DEBUG", "[CONTEXT",
    "SystemMessage", "HumanMessage", "AIMessage",
]

_CODE_LEAK_RE = re.compile(
    r'(?:print\s*\(|default_api\.|get_careers_by_campus\s*\(|get_campus_info\s*\(|'
    r'get_objection_response\s*\(|\w+_api\.\w+\s*\()',
    re.IGNORECASE,
)

_JSON_ARTIFACT_RE = re.compile(r'\{"(?:thought|thinking|reflection|plan)"[^}]*\}', re.IGNORECASE)

_DEFAULT_BOOKING_LINK = "https://link.superleads.mx/widget/booking/o33ctHxdbcr7Q7wmarJY"


def validate_and_clean(
    text: str,
    history: list = None,
    channel: str = "Live_Chat",
) -> tuple[str, bool]:
    """
    Valida y limpia un mensaje ANTES de enviarlo. Última línea de defensa.
    """
    if not text:
        logger.warning("VALIDACION: Mensaje vacio — bloqueado")
        return ("", False)

    original = text

    # 1) SIGNATURE CLEANUP
    text = text.replace('\u200B', '').strip()

    # 2) Empty after cleanup
    if not text.strip():
        logger.warning("VALIDACION: Mensaje vacio despues de limpieza — bloqueado")
        return ("", False)

    # 3) SYSTEM TEXT LEAK
    for pattern in _SYSTEM_LEAK_PATTERNS:
        if pattern in text:
            idx = text.find(']')
            if idx != -1 and idx < len(text) - 10:
                recovered = text[idx+1:].strip().lstrip(':').strip()
                if len(recovered) > 20:
                    logger.warning("VALIDACION: System text leak detectado y recortado")
                    text = recovered
                    break
            logger.warning("VALIDACION: System text leak irrecuperable — bloqueado")
            return ("", False)

    # 4) JSON ARTIFACTS
    text = _JSON_ARTIFACT_RE.sub('', text).strip()
    if not text:
        logger.warning("VALIDACION: Solo contenia JSON artifacts — bloqueado")
        return ("", False)

    # 4.5) CODE LEAK
    if _CODE_LEAK_RE.search(text):
        logger.warning("VALIDACION: Code leak detectado en respuesta — bloqueado: %s", text[:200])
        return ("", False)

    # 5) UNRESOLVED PLACEHOLDERS
    if "{BOOKING_LINK}" in text:
        logger.warning("VALIDACION: {BOOKING_LINK} no resuelto — usando default")
        text = text.replace("{BOOKING_LINK}", _DEFAULT_BOOKING_LINK)

    # 6) LENGTH LIMIT
    if channel in ['IG', 'FB', 'Instagram', 'Facebook Messenger'] and len(text) > 1500:
        logger.warning(f"VALIDACION: Mensaje truncado ({len(text)} -> 1500 chars) para {channel}")
        text = text[:1497] + "..."

    # 7) DUPLICATE CHECK
    if history:
        last_assistant = next((m for m in reversed(history) if m.get('role') == 'assistant'), None)
        if last_assistant and last_assistant.get('content', '').strip() == text.strip():
            logger.warning("VALIDACION: Mensaje duplicado del ultimo envio — bloqueado")
            return ("", False)

    if text != original:
        logger.info(f"VALIDACION: Mensaje limpiado (original: {len(original)} -> limpio: {len(text)})")

    return (text, True)


def inject_booking_link(
    text: str,
    contact_id: str,
    location_id: str,
    detected_campus: str,
    full_name: str,
    history: list,
    ghl_service,
    advisor_service,
) -> str:
    """Resolves {BOOKING_LINK} placeholder in text with actual advisor link."""
    # Check if LLM missed the booking link
    if "{BOOKING_LINK}" not in text:
        data_check = DataExtraction.check_complete_data_in_history(history, full_name)
        if data_check['complete']:
            logger.warning("LLM fallo en enviar BOOKING_LINK pero datos completos detectados!")
            nombre_display = full_name or "amigo/a"
            text = f"¡Gracias {nombre_display}! 🐻 Para que formes parte de la comunidad Grizzlies de Colegio San Ángel, agenda tu cita con un asesor aquí: {{BOOKING_LINK}}"

    if "{BOOKING_LINK}" not in text:
        return text

    # --- PRIORITY 0: Reuse booking link already sent ---
    if history:
        _BOOKING_URL_RE = re.compile(r'https://link\.superleads\.mx/widget/booking/\S+')
        for msg in reversed(history):
            if msg.get('role') == 'assistant':
                match = _BOOKING_URL_RE.search(msg.get('content', ''))
                if match:
                    existing_link = match.group(0)
                    text = text.replace("{BOOKING_LINK}", existing_link)
                    logger.info("Booking link reutilizado de historial: %s", existing_link)
                    return text

    # --- Resolve advisor ---
    advisor = None

    # PRIORITY 1: Assigned advisor in GHL
    try:
        contact_data = ghl_service.get_contact(contact_id, location_id)
        assigned_user_id = contact_data.get("assignedTo") if contact_data else None

        if assigned_user_id:
            logger.info(f"Lead tiene vendedor asignado en GHL: {assigned_user_id}")
            advisor = advisor_service.get_advisor_by_ghl_user(assigned_user_id)
            if advisor:
                logger.info(f"Booking link del vendedor asignado: {advisor.get('name')}")
        else:
            logger.info("Lead sin vendedor asignado en GHL")
    except Exception as e:
        logger.warning(f"Error consultando assignedTo: {e}")

    # PRIORITY 2: Round-robin by location
    if not advisor:
        if detected_campus:
            advisor_loc = ghl_service.get_location_id_for_campus(detected_campus) or location_id
            logger.info(f"Booking por plantel detectado: {detected_campus} -> location: {advisor_loc}")
        else:
            advisor_loc = location_id
            logger.info(f"Plantel no detectado, usando location_id: {advisor_loc}")

        advisor = advisor_service.get_next_advisor(advisor_loc)

    # --- Replace placeholder ---
    if advisor:
        booking_link = advisor.get("booking_link", advisor_service.get_default_booking_link())
        text = text.replace("{BOOKING_LINK}", booking_link)
        advisor_service.increment_advisor_count(advisor.get("id"))
        logger.info(f"Link de asesor: {advisor.get('name')} - {booking_link}")
    else:
        default_link = advisor_service.get_default_booking_link()
        text = text.replace("{BOOKING_LINK}", default_link)
        logger.warning(f"Sin asesor disponible, usando link por defecto: {default_link}")

    return text


def send_response(
    contact_id: str,
    message: str,
    channel: str,
    conversation_id: str,
    location_id: str,
    phone: str,
    ghl_service,
    history: list = None,
) -> bool:
    """Sends a message via GHL with hybrid strategy."""
    message, is_valid = validate_and_clean(message, history, channel)
    if not is_valid:
        logger.warning("Mensaje bloqueado por validacion pre-envio")
        return False

    conv_id_to_use = conversation_id
    if channel in ['WhatsApp', 'SMS'] and phone:
        conv_id_to_use = None
        logger.info(f"Canal {channel} con telefono: Usando contact_id (Legacy Mode)")

    response = ghl_service.send_message(
        contact_id=contact_id,
        message=message,
        message_type=channel,
        conversation_id=conv_id_to_use,
        location_id=location_id
    )

    if response:
        logger.info(f"Mensaje enviado correctamente por {channel}")
        return True

    if not response and phone:
        logger.warning(f"Fallo envio por {channel}, intentando fallback por WhatsApp...")
        ghl_service.send_message(
            contact_id=contact_id,
            message=message,
            message_type='WhatsApp',
            conversation_id=None,
            location_id=location_id
        )
        return True

    return False


def update_tags(
    contact_id: str,
    is_relevant: bool,
    location_id: str,
    ghl_service,
    extra_tag: str = None,
):
    """Update GHL tags based on relevance."""
    if is_relevant:
        ghl_service.remove_tag(contact_id, "No es Ventas", location_id)
        ghl_service.add_tag(contact_id, "Proceso de Ventas", location_id)
    else:
        ghl_service.add_tag(contact_id, "No es Ventas", location_id)
        ghl_service.remove_tag(contact_id, "Proceso de Ventas", location_id)

    if extra_tag:
        ghl_service.add_tag(contact_id, extra_tag, location_id)


def update_scoring_tags(
    contact_id: str,
    score: int,
    location_id: str,
    ghl_service,
):
    """Update lead scoring tags in GHL."""
    from app.services.lead_scoring_service import get_score_tag, ALL_SCORE_TAGS

    new_tag = get_score_tag(score)

    for old_tag in ALL_SCORE_TAGS:
        if old_tag != new_tag:
            ghl_service.remove_tag(contact_id, old_tag, location_id)

    ghl_service.add_tag(contact_id, new_tag, location_id)
    logger.info(f"Score tag actualizado: {new_tag} (score={score})")


def save_ai_response(
    conv_db_id: str,
    ai_response_text: str,
    result: dict | None,
    conversation_service,
):
    """Save AI response to Supabase with optional thought signature metadata."""
    if not conv_db_id:
        return

    metadata = {}
    if result:
        try:
            from app.agents.career_agent import extract_thought_signature
            ai_response_obj = result["messages"][-1]
            thought_sig = extract_thought_signature(ai_response_obj)
            if thought_sig:
                metadata['thought_signature'] = thought_sig
        except Exception as e:
            logger.warning(f"Error extrayendo thought_signature: {e}")

    conversation_service.save_message(conv_db_id, 'assistant', ai_response_text, metadata=metadata)
    logger.info(f"Conversacion guardada en Supabase: {conv_db_id}")
