"""
ConversationOrchestrator: Full conversation pipeline for Colegios San Ángel.
Adapted from Universidad de Oriente version - agent is Luca 🐻 (Grizzlies).
"""

import logging
from datetime import datetime, timedelta, timezone

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.agents.career_agent import career_agent, extract_thought_signature
from app.models.response_models import AgentResponse
from app.utils.data_extraction import DataExtraction
from app.utils.helpers import detect_channel
from app.services.loop_detector import LoopDetector
from app.services import lead_scoring_service
from app.services import safety_net_service
from app.services import response_service
from app.services.payload_service import WebhookData

logger = logging.getLogger(__name__)


class ConversationOrchestrator:
    """Orchestrates the full conversation pipeline, decoupled from HTTP."""

    def __init__(self, ghl_service, conversation_service, advisor_service,
                 lead_state_service, campus_registry):
        self.ghl = ghl_service
        self.conversations = conversation_service
        self.advisors = advisor_service
        self.lead_states = lead_state_service
        self.campus_registry = campus_registry

    # =================================================================
    #  PUBLIC ENTRY POINT
    # =================================================================

    def process(self, data: WebhookData) -> dict:
        """Full pipeline: 12 steps. Returns a JSON-serializable dict."""

        full_name = data.full_name
        contact_id = data.contact_id
        phone = data.phone
        location_id = data.location_id
        message = data.message
        conversation_id = data.conversation_id
        source = data.source
        channel = data.channel
        direction = data.direction
        is_lead_form_message = data.is_lead_form
        lead_form_data = data.lead_form_data

        # --- STEP 1b: Resolve missing conversation_id ---
        if not conversation_id:
            logger.warning("conversation_id vacío, buscando en GHL para contact_id: %s...", contact_id)
            conversation_id = self.ghl.get_conversation_id(contact_id, location_id)
            if conversation_id:
                logger.info("conversation_id recuperado: %s", conversation_id)

        # --- STEP 2: EARLY PERSISTENCE ---
        conv_db_id = self.conversations.get_or_create_conversation(
            contact_id=contact_id,
            location_id=location_id or "unknown",
            channel=source
        )
        if conv_db_id:
            self.conversations.save_message(conv_db_id, "user", message)

        logger.info("Webhook Conversaciones Procesado:")
        logger.info("   %s | %s | %s", full_name, contact_id, channel)
        logger.info("   %s...", message[:80])
        logger.info("-" * 30)

        if not message or not contact_id:
            logger.error("Faltan datos esenciales (message o contact_id)")
            return {"status": "error", "message": "Missing required fields: message or contact_id"}

        # --- STEP 3: LOAD HISTORY & CHECK HUMAN TAKEOVER ---
        logger.info("Cargando historial...")
        history = self.conversations.get_conversation_history(contact_id, limit=20)

        takeover_result = self._check_human_takeover(contact_id, conversation_id, location_id, history)
        if takeover_result:
            return takeover_result

        handoff_result = self._check_handoff_persistence(history)
        if handoff_result:
            return handoff_result

        # --- STEP 4: ADMIN TOPIC FILTER ---
        admin_msg = safety_net_service.check_admin_topic(message)
        if admin_msg:
            logger.info("Tema administrativo detectado: '%s...'", message[:30])
            handoff_msg = "Para dudas sobre trámites escolares, boletas o certificados, por favor contacta directamente a tu plantel."
            self.ghl.send_message(
                contact_id=contact_id, message=handoff_msg,
                message_type=channel, conversation_id=conversation_id,
                location_id=location_id
            )
            self.ghl.add_tag(contact_id, "Necesita Humano", location_id)
            self.ghl.add_tag(contact_id, "Tema Administrativo", location_id)
            if conv_db_id:
                self.conversations.save_message(conv_db_id, "assistant", handoff_msg, metadata={"type": "admin_handoff"})
            return {"status": "ignored", "reason": "admin_topic_handoff"}

        # --- STEP 4b: LEAD STATE PERSISTENCE ---
        lead_state = self.lead_states.get_or_create(contact_id, location_id)
        logger.info("Lead State: step=%s, complete=%s", lead_state.get('current_step', 1), lead_state.get('is_complete', False))

        pre_captured = {}
        if channel in ['WhatsApp', 'SMS'] and phone:
            clean_phone = ''.join(filter(str.isdigit, phone))
            if len(clean_phone) >= 10:
                pre_captured["telefono"] = clean_phone[-10:]
        if is_lead_form_message and lead_form_data:
            if lead_form_data.get('campus'):
                pre_captured["campus"] = lead_form_data['campus']
            if lead_form_data.get('full_name'):
                pre_captured["nombre_completo"] = lead_form_data['full_name']
            if lead_form_data.get('phone'):
                pre_captured["telefono"] = lead_form_data['phone']
            if lead_form_data.get('email'):
                pre_captured["email"] = lead_form_data['email']
            if lead_form_data.get('career_interest'):
                pre_captured["carrera"] = lead_form_data['career_interest']
        if pre_captured:
            self.lead_states.bulk_update(contact_id, pre_captured)
            lead_state = self.lead_states.get_or_create(contact_id, location_id)

        # --- STEP 4c: SOURCE TAGGING (website) ---
        _msg_lower = message.lower()
        if any(kw in _msg_lower for kw in ("sitio web", "página web", "pagina web", "tu web", "su web", "tu sitio", "su sitio")):
            logger.info("Fuente detectada: Sitio Web")
            self.ghl.add_tag(contact_id, "Sitio Web", location_id)

        # --- STEP 5: AI AGENT PIPELINE ---
        ai_response_text = None
        try:
            # Pre-LLM Loop Detection
            if LoopDetector.detect_history_loop(history):
                return self._handle_pre_llm_loop(
                    contact_id, location_id, conversation_id, channel,
                    source, full_name, history, conv_db_id
                )

            # Booking-Sent: Post-Booking
            booking_state = safety_net_service.check_booking_sent_with_state(
                history, lead_state_service=self.lead_states, contact_id=contact_id
            )
            post_booking_mode = False
            if booking_state["sent"]:
                if is_lead_form_message:
                    logger.info("Lead Form detectado POST-BOOKING - Procesando igualmente")
                elif booking_state["post_booking_count"] >= 1:
                    logger.info("Post-booking: 1+ respuestas -> handoff a humano + silencio permanente")
                    handoff_msg = "Un asesor te contactará pronto para cualquier duda adicional. ¡Nos vemos pronto! 🐻"
                    self.ghl.send_message(
                        contact_id=contact_id, message=handoff_msg,
                        message_type=channel, conversation_id=conversation_id,
                        location_id=location_id
                    )
                    self.ghl.add_tag(contact_id, "Lead con cita pendiente", location_id)
                    if conv_db_id:
                        self.conversations.save_message(conv_db_id, "assistant", handoff_msg, metadata={"type": "post_booking_handoff"})
                    self.conversations.set_human_active(contact_id, True)
                    return {"status": "success", "message": "Post-booking handoff", "booking_already_sent": True}
                else:
                    logger.info("Post-booking mode: count=%s", booking_state['post_booking_count'])
                    post_booking_mode = True

            # Campus Detection
            current_campus = self.ghl.get_campus_name(location_id)
            logger.info("Contexto de Plantel: %s", current_campus)

            # SAFETY NET A: Human Request
            if safety_net_service.check_human_request(message):
                logger.info("SAFETY NET (HUMANO): Usuario pide '%s'", message)
                advisor = self.advisors.get_next_advisor(location_id)
                booking_link = advisor.get("booking_link", self.advisors.get_default_booking_link()) if advisor else self.advisors.get_default_booking_link()
                if advisor:
                    self.advisors.increment_advisor_count(advisor.get("id"))
                bypass_text = f"¡Entendido {full_name}! Para que un asesor experto te atienda personalmente, por favor agenda tu cita aquí: {booking_link} 🐻"

                if conv_db_id:
                    self.conversations.save_message(conv_db_id, "assistant", bypass_text)

                response_service.send_response(
                    contact_id=contact_id, message=bypass_text, channel=channel,
                    conversation_id=conversation_id, location_id=location_id,
                    phone=phone, ghl_service=self.ghl
                )
                return {"status": "success", "processed_data": {"ai_response": bypass_text, "safety_net": True}}

            # SAFETY NET B: Complete Data (Phone + Email)
            incoming_phone, incoming_email = safety_net_service.check_complete_data(message, lead_form_data)
            if incoming_phone and incoming_email:
                logger.info("SAFETY NET (DATOS): Teléfono (%s) y Email (%s) detectados", incoming_phone, incoming_email)

                advisor = self.advisors.get_next_advisor(location_id)
                booking_link = advisor.get("booking_link", self.advisors.get_default_booking_link()) if advisor else self.advisors.get_default_booking_link()
                if advisor:
                    self.advisors.increment_advisor_count(advisor.get("id"))

                nombre_display = full_name or "amigo/a"
                bypass_response_text = f"¡Excelente {nombre_display}! 🐻 Ya tengo todos tus datos. Un asesor te dará toda la información personalizada en tu cita, agenda aquí: {booking_link}"

                self.ghl.send_message(
                    contact_id=contact_id, message=bypass_response_text,
                    message_type=channel, conversation_id=conversation_id,
                    location_id=location_id
                )

                if conv_db_id:
                    self.conversations.save_message(conv_db_id, "assistant", bypass_response_text)

                fields_to_update = {"phone": incoming_phone, "email": incoming_email}
                if is_lead_form_message and lead_form_data:
                    if lead_form_data.get('full_name'):
                        fields_to_update["name"] = lead_form_data['full_name']
                        fields_to_update["firstName"] = lead_form_data.get('first_name', '')
                        fields_to_update["lastName"] = lead_form_data.get('last_name', '')
                    logger.info("Actualizando GHL con datos de Lead Form: %s", fields_to_update)
                self.ghl.update_contact_fields(contact_id, fields_to_update, location_id)

                return {"status": "success", "processed_data": {"ai_response": bypass_response_text, "safety_net": True}}

            # BUILD LANGCHAIN HISTORY
            messages_history = self._build_messages_history(history, message)
            logger.info("Historial: %s previos + 1 nuevo", len(history))

            # PHONE INJECTION (WhatsApp/SMS)
            if channel in ['WhatsApp', 'SMS'] and phone:
                clean_phone = ''.join(filter(str.isdigit, phone))
                if len(clean_phone) >= 10:
                    phone_10 = clean_phone[-10:]
                    messages_history.append(SystemMessage(
                        content=f"[SISTEMA - DATO PRE-CAPTURADO]: El WhatsApp del usuario ya está registrado: {phone_10}. "
                                f"NO pidas el número de WhatsApp. "
                                f"IMPORTANTE: Tu PRIMERA pregunta SIEMPRE debe ser confirmar el PLANTEL de interés. "
                                f"Después pide: nivel educativo, nombre completo, email. En ese orden."
                    ))
                    logger.info("Teléfono inyectado: %s", phone_10)

            # LEAD FORM DATA INJECTION
            if is_lead_form_message and lead_form_data:
                form_parts = []
                if lead_form_data.get('campus'):
                    form_parts.append(f"Plantel de interés: {lead_form_data['campus']}")
                if lead_form_data.get('career_interest'):
                    form_parts.append(f"Nivel educativo de interés: {lead_form_data['career_interest']}")
                if lead_form_data.get('full_name'):
                    form_parts.append(f"Nombre completo: {lead_form_data['full_name']}")
                if lead_form_data.get('phone'):
                    form_parts.append(f"Teléfono: {lead_form_data['phone']}")
                if lead_form_data.get('email'):
                    form_parts.append(f"Email: {lead_form_data['email']}")

                if form_parts:
                    messages_history.append(SystemMessage(
                        content=f"[SISTEMA - DATOS PRE-CAPTURADOS DE FORMULARIO LEAD ADS]:\n"
                                f"{chr(10).join(form_parts)}\n"
                                f"IMPORTANTE: Estos datos YA fueron proporcionados por el prospecto. "
                                f"NO los pidas de nuevo. Usa esta información para avanzar directo "
                                f"a los datos faltantes o al link de cita si ya tienes todo."
                    ))
                    logger.info("Lead Form data inyectados: %s", ', '.join(form_parts))

            # INVOKE AI AGENT
            initial_state = {
                "messages": messages_history,
                "contact_id": contact_id,
                "user_name": full_name or "Usuario",
                "post_context": "",
                "current_campus": current_campus,
                "location_id": location_id,
                "lead_state": lead_state,
                "post_booking_mode": post_booking_mode,
            }

            try:
                result = career_agent.invoke(initial_state)
                ai_response = result["messages"][-1]
                structured_response = result.get("structured_response")
            except Exception as e:
                logger.error("Error en Agente Gemini: %s", e)
                ai_response_text = "¡Hola! Tuve un pequeño problema técnico. ¿Podrías repetir tu mensaje? 🐻"
                structured_response = AgentResponse(is_relevant_query=True, detected_campus="", message=ai_response_text)
                ai_response = type('obj', (object,), {'content': ai_response_text})()
                result = None

            ai_response_text = str(ai_response.content).replace('\u200B', '').strip()

            # POST-LLM LOOP PREVENTION
            is_progressing = incoming_email or incoming_phone
            if not is_progressing and LoopDetector.detect_loop(history, ai_response_text):
                return self._handle_post_llm_loop(
                    ai_response_text, contact_id, location_id, conversation_id,
                    channel, source, full_name, history, conv_db_id
                )

            logger.info("Respuesta IA: %s", ai_response_text)
            logger.info("Consulta Relevante: %s", structured_response.is_relevant_query if structured_response else 'N/A')

            # UPDATE CONTACT FIELDS
            if structured_response and hasattr(structured_response, 'captured_data') and structured_response.captured_data:
                logger.info("Datos capturados: %s", structured_response.captured_data)
                self.ghl.update_contact_fields(contact_id, structured_response.captured_data, location_id)

            # UPDATE LEAD STATE
            update_data = {}
            if structured_response:
                if hasattr(structured_response, 'captured_data') and structured_response.captured_data:
                    update_data.update(structured_response.captured_data)
                if structured_response.detected_campus:
                    update_data["detected_campus"] = structured_response.detected_campus
            if update_data:
                self.lead_states.bulk_update(contact_id, update_data)
                lead_state = self.lead_states.get_or_create(contact_id, location_id)

            # MARK BOOKING SENT
            if "{BOOKING_LINK}" in str(ai_response.content) or (ai_response_text and "link.superleads.mx/widget/booking" in ai_response_text):
                self.lead_states.set_booking_sent(contact_id)

            # POST-BOOKING COUNT
            if post_booking_mode:
                self.lead_states.increment_post_booking_count(contact_id)

            # LEAD SCORING
            try:
                score = lead_scoring_service.calculate_score(
                    lead_state=lead_state,
                    message=message,
                    channel=channel,
                    is_lead_form=is_lead_form_message,
                    lead_form_data=lead_form_data,
                )
                self.lead_states.update_score(contact_id, score)
                logger.info("Lead Score: %s -> %s", score, lead_scoring_service.get_score_tag(score))
            except Exception as e:
                logger.warning("Error calculando score: %s", e)
                score = 0

            # CAMPUS TRANSFER
            detected_campus = structured_response.detected_campus if structured_response else ""
            if detected_campus:
                transfer_result = self._handle_campus_transfer(
                    detected_campus, contact_id, location_id, conversation_id,
                    source, channel, full_name, message, history
                )
                if transfer_result:
                    contact_id = transfer_result.get("new_contact_id", contact_id)
                    location_id = transfer_result.get("new_location_id", location_id)

            # BOOKING LINK INJECTION
            ai_response_text = response_service.inject_booking_link(
                text=ai_response_text,
                contact_id=contact_id,
                location_id=location_id,
                detected_campus=detected_campus,
                full_name=full_name,
                history=history,
                ghl_service=self.ghl,
                advisor_service=self.advisors,
            )

            # SEND RESPONSE
            has_booking_link = "http" in ai_response_text or "Agenda tu cita" in ai_response_text
            if structured_response and (structured_response.is_relevant_query or has_booking_link or is_lead_form_message):
                if is_lead_form_message and not structured_response.is_relevant_query:
                    logger.warning("FORZANDO ENVIO POR LEAD FORM: Formulario siempre es prospecto relevante.")
                elif not structured_response.is_relevant_query and has_booking_link:
                    logger.warning("FORZANDO ENVIO POR BOOKING LINK.")
                logger.info("Enviando respuesta...")

                sent = response_service.send_response(
                    contact_id=contact_id, message=ai_response_text, channel=channel,
                    conversation_id=conversation_id, location_id=location_id,
                    phone=phone, ghl_service=self.ghl
                )

                if not sent:
                    logger.warning("Respuesta bloqueada por validacion, enviando fallback")
                    fallback_msg = "¡Gracias por tu interés! ¿Podrías repetirme tu consulta para ayudarte mejor? 🐻"
                    response_service.send_response(
                        contact_id=contact_id, message=fallback_msg, channel=channel,
                        conversation_id=conversation_id, location_id=location_id,
                        phone=phone, ghl_service=self.ghl
                    )
                    ai_response_text = fallback_msg

                response_service.update_tags(contact_id, True, location_id, self.ghl)

                try:
                    response_service.update_scoring_tags(contact_id, score, location_id, self.ghl)
                except Exception as e:
                    logger.warning("Error actualizando scoring tags: %s", e)

                conv_id = self.conversations.get_or_create_conversation(
                    contact_id=contact_id, location_id=location_id or "unknown", channel=source
                )
                response_service.save_ai_response(conv_id, ai_response_text, result, self.conversations)

            else:
                logger.info("Consulta no relevante - Enviando respuesta de redirección cálida")
                response_service.send_response(
                    contact_id=contact_id, message=ai_response_text, channel=channel,
                    conversation_id=conversation_id, location_id=location_id,
                    phone=phone, ghl_service=self.ghl
                )
                response_service.update_tags(contact_id, False, location_id, self.ghl)
                self.ghl.add_tag(contact_id, "No Prospecto", location_id)
                conv_id = self.conversations.get_or_create_conversation(
                    contact_id=contact_id, location_id=location_id or "unknown", channel=source
                )
                if conv_id:
                    self.conversations.save_message(conv_id, "assistant", ai_response_text, metadata={"type": "not_relevant_redirect"})

        except Exception as e:
            logger.error("Error en Agente/Envío: %s", e)
            logger.exception("Traceback:")

        return {
            "status": "success",
            "processed_data": {
                "full_name": full_name, "contact_id": contact_id,
                "message": message, "conversation_id": conversation_id,
                "source": source, "direction": direction,
                "ai_response": ai_response_text
            }
        }

    # =================================================================
    #  HELPER METHODS
    # =================================================================

    @staticmethod
    def _build_messages_history(history: list, current_message: str) -> list:
        """Convert Supabase history to LangChain messages with consecutive-role fusion."""
        messages_history = []
        for msg in history:
            role = msg['role']
            content = msg['content']

            metadata = msg.get('metadata', {})
            additional_kwargs = {}
            if metadata and 'thought_signature' in metadata:
                additional_kwargs['__gemini_function_call_thought_signatures__'] = metadata['thought_signature']

            if messages_history:
                last_msg = messages_history[-1]
                if (role == 'user' and isinstance(last_msg, HumanMessage)) or \
                   (role == 'assistant' and isinstance(last_msg, AIMessage)):
                    last_msg.content += f"\n\n{content}"
                    if additional_kwargs and not last_msg.additional_kwargs:
                        last_msg.additional_kwargs = additional_kwargs
                    continue

            if role == 'user':
                messages_history.append(HumanMessage(content=content))
            else:
                messages_history.append(AIMessage(content=content, additional_kwargs=additional_kwargs))

        if messages_history and isinstance(messages_history[-1], HumanMessage):
            messages_history[-1].content += f"\n\n{current_message}"
        else:
            messages_history.append(HumanMessage(content=current_message))

        return messages_history

    def _check_human_takeover(self, contact_id: str, conversation_id: str, location_id: str, history: list) -> dict | None:
        """Check if a human agent has taken over the conversation."""
        try:
            if self.conversations.check_human_active(contact_id):
                logger.info("HUMAN TAKEOVER (Flag en BD) - Bot silenciado")
                return {"status": "ignored", "reason": "human_agent_active", "message": "Human agent flag active"}
        except Exception as e:
            logger.error("Error CRITICO verificando human_active flag: %s — Bot silenciado por precaución", e)
            return {"status": "ignored", "reason": "human_check_error", "message": "Could not verify human flag, silencing bot"}

        try:
            if not conversation_id:
                logger.warning("conversation_id vacío — no se puede verificar intervención humana en GHL")
                return None

            ghl_messages = self.ghl.get_conversation_messages(conversation_id, location_id, limit=20)

            if ghl_messages:
                if isinstance(ghl_messages, dict):
                    ghl_messages = ghl_messages.get('messages', [])
                if not isinstance(ghl_messages, list):
                    ghl_messages = []

                if ghl_messages:
                    ghl_messages.sort(key=lambda x: x.get('dateAdded', ''), reverse=True)

                    IGNORED_SYSTEM_MESSAGES = [
                        "Opportunity", "Stage", "Appointment", "Tag", "Note",
                        "Call", "Voicemail", "Manual Action", "Workflow",
                        "Invoice", "Payment", "Task", "Moved from", "moved from",
                        "✨", "Bienvenido", "bienvenido",
                        "Para brindarte", "para brindarte",
                        "👋 ¡Gracias por tu interés"
                    ]

                    last_outbound = next((
                        m for m in ghl_messages
                        if m.get('direction') == 'outbound'
                        and not any(m.get('body', '').strip().startswith(ignored) for ignored in IGNORED_SYSTEM_MESSAGES)
                    ), None)

                    if last_outbound:
                        outbound_body = last_outbound.get('body', '').strip()

                        is_bot_message = self.conversations.is_message_exists(
                            conversation_id=conversation_id,
                            content=outbound_body,
                            role="assistant"
                        )

                        if not is_bot_message:
                            body_stripped = outbound_body.strip()
                            is_system_msg = any(body_stripped.startswith(ignored) for ignored in IGNORED_SYSTEM_MESSAGES)

                            # Bot signature check: Luca uses 🐻
                            if not is_system_msg:
                                bot_signatures = ["🐻", "Soy Luca", "Luca 🐻", "{BOOKING_LINK}"]
                                if any(sig in body_stripped for sig in bot_signatures):
                                    is_system_msg = True
                                    logger.info("Mensaje con firma del bot (🐻/Luca) no en BD — race condition: '%s'", outbound_body[:80])

                            if not is_system_msg:
                                # Two-tier workflow detection
                                strong_workflow_patterns = [
                                    "📍 Poza Rica", "📍 Coatzacoalcos", "📍 Puebla",
                                    "wa.me/",
                                ]
                                weak_workflow_patterns = [
                                    "Colegio San Ángel", "Colegio San Angel",
                                    "comunidad Grizzlies",
                                    "plantel de tu interés", "atención personalizada",
                                    "Agenda tu cita",
                                ]
                                lead_form_patterns = [
                                    "Completé el formulario",
                                    "Source URL:", "Headline:",
                                    "first_name:", "last_name:",
                                    "phone_number:", "email:",
                                    "elige_tu_campus",
                                ]

                                if any(p in body_stripped for p in strong_workflow_patterns):
                                    is_system_msg = True
                                    logger.warning("Mensaje de WORKFLOW GHL (strong pattern): '%s'", outbound_body[:80])
                                elif sum(1 for p in weak_workflow_patterns if p in body_stripped) >= 2:
                                    is_system_msg = True
                                    logger.warning("Mensaje de WORKFLOW GHL (2+ weak patterns): '%s'", outbound_body[:80])
                                elif any(p in body_stripped for p in lead_form_patterns):
                                    is_system_msg = True
                                    logger.warning("Mensaje de LEAD FORM GHL (filtrado): '%s'", outbound_body[:80])

                            if not is_system_msg:
                                outbound_time_str = last_outbound.get('dateAdded', '')
                                last_outbound_time = datetime.fromisoformat(outbound_time_str.replace('Z', '+00:00'))
                                now_utc = datetime.now(timezone.utc)
                                time_diff = now_utc - last_outbound_time

                                if time_diff.total_seconds() < 90:
                                    logger.info("Outbound reciente (%.1fs < 90s) no verificado en BD — grace period: '%s'",
                                                time_diff.total_seconds(), outbound_body[:80])
                                else:
                                    logger.info("INTERVENCION HUMANA DETECTADA")
                                    logger.info("   Mensaje: '%s'", outbound_body[:80])
                                    logger.info("   Hace: %.1f horas", time_diff.total_seconds() / 3600)

                                    flag_saved = False
                                    for attempt in range(2):
                                        if self.conversations.set_human_active(contact_id, True):
                                            flag_saved = True
                                            break
                                        logger.warning("Intento %s de set_human_active falló, reintentando...", attempt + 1)

                                    if not flag_saved:
                                        logger.error("CRITICO: No se pudo persistir human_active flag para %s", contact_id)

                                    return {"status": "ignored", "reason": "human_agent_active"}
                            else:
                                logger.info("Ultimo mensaje fue del Bot (Validado). Continuando...")
        except Exception as e:
            logger.warning("Error verificando intervención humana en GHL: %s", e)
            logger.exception("Traceback:")

        return None

    @staticmethod
    def _check_handoff_persistence(history: list) -> dict | None:
        """Check if conversation is in handoff state."""
        HANDOFF_MESSAGES = [
            "Un asesor especializado atenderá",
            "Para dudas sobre trámites escolares",
            "Para que un asesor experto te ayude mejor, agenda tu cita",
            "¡Pronto te contactarán!",
            "para ayudarte mejor te conecto con un asesor experto",
            "un asesor especializado se pondrá en contacto",
            "Un asesor te contactará pronto para cualquier duda adicional",
        ]

        if not history:
            return None

        last_assistant_msg = next((m for m in reversed(history) if m['role'] == 'assistant'), None)
        if not last_assistant_msg:
            return None

        last_content = last_assistant_msg.get('content', '')
        is_handoff = any(handoff in last_content for handoff in HANDOFF_MESSAGES)

        if not is_handoff:
            return None

        last_created_at = last_assistant_msg.get('created_at')
        if last_created_at:
            try:
                last_time = datetime.fromisoformat(last_created_at.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                diff = now - last_time
                if diff > timedelta(minutes=30):
                    logger.warning("Handoff EXPIRADO (%.1f min) - Reactivando bot", diff.total_seconds() / 60)
                    return None
            except Exception as e:
                logger.warning("Error parseando fecha: %s", e)

        logger.info("Conversación en estado de HANDOFF ACTIVO - Ignorando")
        return {"status": "ignored", "reason": "handoff_persistence"}

    def _handle_pre_llm_loop(self, contact_id, location_id, conversation_id,
                             channel, source, full_name, history, conv_db_id) -> dict:
        """Handle loop detected BEFORE invoking the LLM."""
        data_check = DataExtraction.check_complete_data_in_history(history, full_name)
        handoff_channel = detect_channel(source)

        if data_check['has_campus'] or data_check['has_career']:
            logger.info("Bucle detectado CON datos parciales - Agendando cita + handoff")
            advisor_location_id = location_id
            import re as _re
            name_to_id = self.campus_registry.get_name_to_id_map()
            full_text_lower = " ".join([m['content'].lower() for m in history])
            for keyword, loc_id in name_to_id.items():
                if _re.search(r'\b' + _re.escape(keyword) + r'\b', full_text_lower):
                    advisor_location_id = loc_id
                    break

            advisor = self.advisors.get_next_advisor(advisor_location_id)
            booking_link = advisor.get("booking_link", self.advisors.get_default_booking_link()) if advisor else self.advisors.get_default_booking_link()
            if advisor:
                self.advisors.increment_advisor_count(advisor.get("id"))

            nombre_display = full_name or "amigo/a"
            loop_handoff_message = f"¡Gracias {nombre_display} por tu interés! 🐻 Para que un asesor experto te ayude mejor, agenda tu cita aquí: {booking_link}"
        else:
            logger.info("Bucle detectado SIN datos - Solo handoff")
            loop_handoff_message = "Un asesor especializado atenderá tus dudas mejor. ¡Pronto te contactarán! 🐻"

        self.ghl.send_message(
            contact_id=contact_id, message=loop_handoff_message,
            message_type=handoff_channel, conversation_id=conversation_id,
            location_id=location_id
        )
        self.ghl.add_tag(contact_id, "Necesita Humano", location_id)

        if conv_db_id:
            self.conversations.save_message(conv_db_id, "assistant", loop_handoff_message, metadata={"type": "loop_handoff"})

        return {
            "status": "ignored", "reason": "loop_detected_handoff",
            "booking_sent": data_check['has_campus'] or data_check['has_career']
        }

    def _handle_post_llm_loop(self, ai_response_text, contact_id, location_id,
                              conversation_id, channel, source, full_name,
                              history, conv_db_id) -> dict:
        """Handle loop detected AFTER the LLM response."""
        logger.info("Loop Preventivo Activado: Bloqueando respuesta repetitiva")

        if safety_net_service.is_greeting_loop(ai_response_text):
            logger.info("Recuperación de Loop de Saludo: Forzando pregunta de nivel educativo.")
            fallback_msg = "¡Excelente! ¿Podrías confirmarme qué nivel educativo te interesa para tu hijo/a?"

            if conv_db_id:
                self.conversations.save_message(conv_db_id, "assistant", fallback_msg)

            self.ghl.send_message(
                contact_id=contact_id, message=fallback_msg,
                message_type=channel, conversation_id=conversation_id,
                location_id=location_id
            )
            return {"status": "success", "processed_data": {"ai_response": fallback_msg, "recovery": True}}

        data_check_proactive = DataExtraction.check_complete_data_in_history(history, full_name)

        if data_check_proactive['has_campus'] or data_check_proactive['has_career']:
            advisor = self.advisors.get_next_advisor(location_id)
            booking_link = advisor.get("booking_link", self.advisors.get_default_booking_link()) if advisor else self.advisors.get_default_booking_link()
            handoff_msg = f"Entiendo, para brindarte una mejor atención, un asesor experto te ayudará personalmente. Agenda tu cita aquí: {booking_link} 🐻"
        else:
            handoff_msg = "Entiendo, para brindarte una mejor atención, un asesor especializado se pondrá en contacto contigo muy pronto. 🐻"

        self.ghl.send_message(
            contact_id=contact_id, message=handoff_msg,
            message_type=channel, conversation_id=conversation_id,
            location_id=location_id
        )
        self.ghl.add_tag(contact_id, "Necesita Humano", location_id)

        return {"status": "ignored", "reason": "proactive_loop_prevention"}

    def _handle_campus_transfer(self, detected_campus, contact_id, location_id,
                                conversation_id, source, channel, full_name,
                                message, history) -> dict | None:
        """Handle campus transfer if detected campus differs from current location."""
        logger.info("Plantel detectado: %s", detected_campus)
        target_location = self.ghl.get_location_id_for_campus(detected_campus)

        if not target_location or target_location == location_id:
            return None

        logger.info("Transferencia necesaria: origen=%s -> destino=%s", location_id, target_location)

        transfer_history = self.conversations.get_conversation_history(contact_id, limit=50)
        transfer_history.append({'role': 'user', 'content': message})

        original_contact_data = self.ghl.get_contact(contact_id, location_id)

        transfer_notice = "Estás siendo transferido a otro plantel, un asesor de ese plantel te contactará 🐻"
        transfer_channel = detect_channel(source)

        self.ghl.send_message(
            contact_id=contact_id, message=transfer_notice,
            message_type=transfer_channel, conversation_id=conversation_id,
            location_id=location_id
        )

        new_contact_id, new_location_id = self.ghl.transfer_contact_to_campus(
            contact_id=contact_id, source_location_id=location_id, target_campus=detected_campus
        )

        if not new_contact_id:
            return None

        self.conversations.migrate_conversation(
            old_contact_id=contact_id,
            new_contact_id=new_contact_id,
            new_location_id=new_location_id
        )

        if transfer_history:
            history_summary = "📋 HISTORIAL DE CONVERSACIÓN TRANSFERIDO:\n\n"
            for msg in transfer_history:
                role_emoji = "👤" if msg['role'] == 'user' else "🤖"
                role_label = "Usuario" if msg['role'] == 'user' else "Luca"
                content = msg['content'][:500]
                history_summary += f"{role_emoji} {role_label}: {content}\n\n"
            history_summary += "─────────────────────────\n⬆️ Historial anterior del prospecto"

            if transfer_channel == 'WhatsApp':
                new_conversation_id = self.ghl.get_conversation_id(new_contact_id, new_location_id)
                self.ghl.send_message(
                    contact_id=new_contact_id, message=history_summary,
                    message_type=transfer_channel, conversation_id=new_conversation_id,
                    location_id=new_location_id
                )
            else:
                campus_origen = self.ghl.get_campus_name(location_id)
                canal_display = "Instagram" if transfer_channel == 'IG' else "Facebook Messenger"

                social_username = ""
                if original_contact_data:
                    social_username = (
                        original_contact_data.get('instagram', '') or
                        original_contact_data.get('instagramUrl', '') or
                        original_contact_data.get('facebook', '') or
                        original_contact_data.get('facebookUrl', '') or
                        original_contact_data.get('socialMedia', {}).get('instagram', '') or
                        original_contact_data.get('name', '') or
                        full_name or ''
                    )

                note_content = f"🔔 PROSPECTO TRANSFERIDO DESDE {campus_origen.upper()}\n"
                note_content += f"📱 Canal de origen: {canal_display}\n"
                if social_username:
                    note_content += f"👤 Usuario/Perfil: {social_username}\n"
                note_content += f"⚠️ IMPORTANTE: El contacto fue originado por {canal_display}.\n"
                note_content += f"   → Contactar por teléfono/email, o esperar que reinicie conversación.\n\n"
                note_content += "─────────────────────────\n"
                note_content += history_summary

                self.ghl.add_note(contact_id=new_contact_id, note_body=note_content, location_id=new_location_id)
                self.ghl.update_contact_field(
                    contact_id=new_contact_id, field_key="notas",
                    value=note_content, location_id=new_location_id
                )

        logger.info("Transferencia completada -> %s", new_contact_id)
        return {"new_contact_id": new_contact_id, "new_location_id": new_location_id}
