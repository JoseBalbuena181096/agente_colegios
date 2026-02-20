"""
PayloadService: Extracts and normalizes data from incoming webhook payloads.
Handles direction/type filtering, lead form detection, and channel normalization.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from app.utils.helpers import get_nested_value, get_value_flexible, detect_channel

logger = logging.getLogger(__name__)


# --- REACTION / LIKE / STORY MENTION DETECTOR ---

# Single emoji regex (covers most common emoji ranges + variation selectors)
_EMOJI_ONLY_RE = re.compile(
    r'^[\s]*'
    r'[\U0001F600-\U0001F64F'   # Emoticons
    r'\U0001F300-\U0001F5FF'     # Misc Symbols
    r'\U0001F680-\U0001F6FF'     # Transport & Map
    r'\U0001F900-\U0001F9FF'     # Supplemental
    r'\U0001FA00-\U0001FA6F'     # Chess, Extended-A
    r'\U0001FA70-\U0001FAFF'     # Extended-A cont.
    r'\U00002702-\U000027B0'     # Dingbats
    r'\U0000FE00-\U0000FE0F'     # Variation Selectors
    r'\U0000200D'                # ZWJ
    r'\U00002600-\U000026FF'     # Misc symbols
    r'\U00002764'                # Heart
    r'\U0000FE0F'                # Variation selector
    r']+[\s]*$'
)

_REACTION_KEYWORDS = [
    "mención de la historia",
    "mencion de la historia",
    "story_mention",
    "story_reply",
    "reacted to your message",
    "reaccionó a tu mensaje",
    "le dio me gusta a tu mensaje",
    "liked your message",
    "le gustó tu mensaje",
]

_REACTION_CONTENT_TYPES = [
    "reaction", "story_mention", "story_reply", "like",
    "ig_story_mention", "ig_story_reply",
    "fb_reaction", "ig_reaction",
]


def _is_reaction_or_like(message: str, raw_body: dict) -> bool:
    """
    Detect if a message is a reaction, like, or story mention from FB/IG.
    These should be ignored by the AI agent.
    """
    msg_lower = message.lower().strip()
    
    # 1) Content type in payload
    content_type = (
        raw_body.get('contentType', '') or
        raw_body.get('content_type', '') or
        get_nested_value(raw_body, ['customData', 'contentType']) or
        raw_body.get('messageType', '') or
        ''
    ).lower()
    
    if content_type in _REACTION_CONTENT_TYPES:
        logger.info("Content type '%s' = reacción/like", content_type)
        return True
    
    # 2) Known reaction keywords in message text
    if any(kw in msg_lower for kw in _REACTION_KEYWORDS):
        logger.info("Keyword de reacción/mención detectado en texto")
        return True
    
    # 3) Single emoji (1-3 emojis with no other text = reaction)
    if len(msg_lower) <= 12 and _EMOJI_ONLY_RE.match(message):
        logger.info("Mensaje es solo emoji(s) = reacción: '%s'", message)
        return True
    
    # 4) GHL-specific: check 'type' field for story/reaction indicators
    msg_type = (raw_body.get('type', '') or '').lower()
    if msg_type in ('story_mention', 'story_reply', 'reaction'):
        logger.info("Payload type '%s' = reacción/story", msg_type)
        return True
    
    return False


# --- LEAD FORM PARSER ---

_LEAD_INDICATORS = ["Source URL:", "Completé el formulario", "elige_tu_campus", "first_name:", "last_name:", "Headline:"]

def parse_lead_form(message: str) -> dict | None:
    """
    Detecta y parsea mensajes de Lead Forms (Facebook/Instagram Lead Ads).
    Estos mensajes llegan con formato 'campo:: valor' o 'campo: valor'.
    
    Returns:
        dict con campos extraídos o None si no es un Lead Form.
    """
    if not message or not isinstance(message, str):
        return None
    
    if not any(indicator in message for indicator in _LEAD_INDICATORS):
        return None
    
    fields = {}
    for line in message.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        if '::' in line:
            parts = line.split('::', 1)
        elif ':' in line and not line.startswith('http'):
            parts = line.split(':', 1)
        else:
            continue
        
        if len(parts) == 2:
            key = parts[0].strip().lower().replace(' ', '_')
            val = parts[1].strip()
            if val:
                fields[key] = val
    
    if not fields:
        return None
    
    # Extract career interest from various field names
    career_interest = ''
    for key, val in fields.items():
        if any(kw in key for kw in ['interés', 'interes', 'carrera', 'nivel', 'grado', 'nivel_educativo', 'programa']):
            if key not in ('elige_tu_campus_más_cercano', 'elige_tu_campus_mas_cercano', 'campus'):
                career_interest = val
                break

    result = {
        'is_lead_form': True,
        'campus': fields.get('elige_tu_campus_más_cercano', fields.get('elige_tu_campus_mas_cercano', fields.get('campus', ''))),
        'first_name': fields.get('first_name', ''),
        'last_name': fields.get('last_name', ''),
        'full_name': f"{fields.get('first_name', '')} {fields.get('last_name', '')}".strip(),
        'phone': fields.get('phone_number', fields.get('phone', fields.get('telefono', ''))),
        'email': fields.get('email', fields.get('correo', '')),
        'career_interest': career_interest,
        'source_url': fields.get('source_url', ''),
        'raw_fields': fields
    }
    
    logger.info("LEAD FORM PARSEADO: campus=%s, nombre=%s, tel=%s, email=%s", result['campus'], result['full_name'], result['phone'], result['email'])
    return result


# --- WEBHOOK DATA ---

@dataclass
class WebhookData:
    """Normalized data extracted from a GHL webhook payload."""
    # Contact info
    full_name: str = ""
    contact_id: str = ""
    phone: str = ""
    location_id: str = ""
    
    # Message
    message: str = ""
    direction: str = ""
    message_type: str = ""
    conversation_id: str = ""
    source: str = "unknown"
    channel: str = "Live_Chat"
    
    # Lead Form
    lead_form_data: Optional[dict] = None
    is_lead_form: bool = False
    
    # Filtering
    should_ignore: bool = False
    ignore_reason: str = ""
    
    # Raw payload (kept for edge cases)
    raw_body: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def ignore_response(self) -> dict:
        return {"status": "ignored", "reason": self.ignore_reason}


def extract_webhook_data(raw_body: dict) -> WebhookData:
    """
    Extract and normalize all data from a webhook payload.
    Handles direction/type filtering, lead form detection, and channel normalization.
    """
    data = WebhookData(raw_body=raw_body)
    
    # --- DIRECTION & TYPE ---
    data.direction = raw_body.get('direction') or get_nested_value(raw_body, ['customData', 'direction']) or ''
    data.message_type = raw_body.get('type') or get_nested_value(raw_body, ['customData', 'type']) or ''
    
    # --- EARLY MESSAGE EXTRACTION (for anti-loop check) ---
    temp_message = raw_body.get('message_body') or get_nested_value(raw_body, ['customData', 'message_body']) or raw_body.get('message')
    
    # --- ANTI-LOOP: OUTBOUND FILTER ---
    if data.direction == 'outbound':
        is_lead_form_outbound = False
        if temp_message and isinstance(temp_message, str):
            if any(kw in temp_message for kw in _LEAD_INDICATORS):
                is_lead_form_outbound = True
                logger.info("Mensaje Outbound identificado como LEAD FORM (Excepción Anti-Bucle)")
        
        if not is_lead_form_outbound:
            logger.warning("Mensaje saliente del agente - ignorando para evitar bucle")
            data.should_ignore = True
            data.ignore_reason = "outbound message"
            return data
    
    # --- ANTI-LOOP: AGENT/SYSTEM TYPE FILTER ---
    if data.message_type in ('agent', 'system'):
        is_lead_form_type = (
            temp_message and isinstance(temp_message, str)
            and any(kw in temp_message for kw in _LEAD_INDICATORS)
        )
        
        if is_lead_form_type:
            logger.info("Mensaje type='%s' identificado como LEAD FORM (Excepción Anti-Bucle)", data.message_type)
        else:
            logger.warning("Mensaje del agente/sistema - ignorando")
            data.should_ignore = True
            data.ignore_reason = "agent message"
            return data
    
    # --- CONTACT DATA ---
    data.full_name = raw_body.get('full_name') or get_value_flexible(raw_body, 'full_name') or raw_body.get('contact_name') or ''
    data.contact_id = raw_body.get('contact_id') or get_value_flexible(raw_body, 'contact_id') or ''
    data.phone = raw_body.get('phone') or get_nested_value(raw_body, ['customData', 'phone']) or ''
    data.location_id = get_value_flexible(raw_body, 'location_id') or ''
    
    # --- MESSAGE ---
    message = raw_body.get('message_body') or get_nested_value(raw_body, ['customData', 'message_body']) or raw_body.get('message')
    
    # Validation: message must be string
    if isinstance(message, dict):
        message = message.get('body', '')
    
    if not message or (isinstance(message, str) and not message.strip()):
        logger.warning("Mensaje vacío o tipo no soportado - ignorando")
        data.should_ignore = True
        data.ignore_reason = "empty message"
        return data
    
    data.message = message
    
    # --- REACTION / LIKE / STORY MENTION FILTER ---
    # Facebook & Instagram send reactions, likes, and story mentions as messages.
    # These should NOT trigger the AI agent.
    if _is_reaction_or_like(message, raw_body):
        logger.info("Reacción/Like/Mención detectada - ignorando: '%s'", message[:50])
        data.should_ignore = True
        data.ignore_reason = "reaction_or_like"
        return data
    
    # --- CONVERSATION METADATA ---
    data.conversation_id = raw_body.get('conversation_id') or get_nested_value(raw_body, ['customData', 'conversation_id']) or ''
    data.source = raw_body.get('source') or get_nested_value(raw_body, ['customData', 'source']) or 'unknown'
    
    # --- LEAD FORM PARSING ---
    data.lead_form_data = parse_lead_form(message)
    data.is_lead_form = data.lead_form_data is not None
    
    if data.is_lead_form:
        logger.info("Lead Form detectado - Datos pre-parseados disponibles")
        if not data.full_name and data.lead_form_data.get('full_name'):
            data.full_name = data.lead_form_data['full_name']
        if not data.phone and data.lead_form_data.get('phone'):
            data.phone = data.lead_form_data['phone']
    
    # --- SOURCE FALLBACK ---
    if data.source in ('unknown', ''):
        data.source = (
            get_nested_value(raw_body, ['contact', 'attributionSource', 'medium']) or
            get_nested_value(raw_body, ['contact', 'lastAttributionSource', 'medium']) or
            raw_body.get('type') or
            raw_body.get('messageType') or
            get_nested_value(raw_body, ['customData', 'type']) or
            get_nested_value(raw_body, ['customData', 'messageType']) or
            'unknown'
        )
    
    # --- CHANNEL NORMALIZATION ---
    data.channel = detect_channel(data.source)
    logger.info("Canal detectado y normalizado: %s (source original: %s)", data.channel, data.source)
    
    return data
