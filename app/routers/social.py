import logging

from fastapi import APIRouter, Request
from langchain_core.messages import HumanMessage
from app.agents.comment_agent import comment_agent
from app.dependencies import ghl_service, apify_service
from app.utils.helpers import get_nested_value

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/webhook_facebook")
async def receive_webhook_facebook(request: Request):
    """
    Webhook específico para COMENTARIOS DE FACEBOOK.
    Recibe comentarios en posts/reels de Facebook, procesa con IA y actualiza campo personalizado.
    El Workflow de GHL se encarga de enviar la respuesta pública.
    """
    # Obtener el JSON crudo
    raw_body = await request.json()
    
    # Lógica de extracción robusta para comentarios de Facebook (Busca en varios lugares)
    
    # 1. Mensaje (Puede estar en triggerData para comentarios de FB)
    message = None
    # Intento A: triggerData (Estructura específica de FB Comment)
    message = get_nested_value(raw_body, ['triggerData', 'fbCommentOnPost', 'fb', 'body'])
    # Intento B: customData
    if not message:
        message = get_nested_value(raw_body, ['customData', 'message_body'])
    # Intento C: Root
    if not message:
        message = raw_body.get('message_body')

    # 2. Location ID
    location_id = None
    location_id = get_nested_value(raw_body, ['location', 'id'])
    if not location_id:
        location_id = get_nested_value(raw_body, ['customData', 'location_id'])
    if not location_id:
        location_id = raw_body.get('location_id')

    # 3. Datos simples (Generalmente están en root si coinciden)
    full_name = raw_body.get('full_name') or get_nested_value(raw_body, ['customData', 'full_name'])
    contact_id = raw_body.get('contact_id') or get_nested_value(raw_body, ['customData', 'contact_id'])
    phone = raw_body.get('phone') or get_nested_value(raw_body, ['customData', 'phone'])
    event_type = raw_body.get('event_type') or get_nested_value(raw_body, ['customData', 'event_type'])

    # 4. Metadatos del Post (Si existen)
    page_id = get_nested_value(raw_body, ['triggerData', 'fbCommentOnPost', 'fb', 'pageId'])
    post_id = get_nested_value(raw_body, ['triggerData', 'fbCommentOnPost', 'fb', 'postId'])
    post_url = get_nested_value(raw_body, ['triggerData', 'fbCommentOnPost', 'fb', 'permalinkUrl'])
    
    # Logs limpios con los datos finales encontrados
    logger.info("Webhook Facebook (Comentarios) Procesado:")
    logger.info(f"   Nombre: {full_name}")
    logger.info(f"   Contact ID: {contact_id}")
    logger.info(f"   Mensaje Recibido: {message}")
    logger.info(f"   Telefono: {phone}")
    logger.info(f"   Location ID: {location_id}")
    logger.info(f"   Tipo de Evento: {event_type}")
    logger.info(f"   Page ID: {page_id}")
    logger.info(f"   Post ID: {post_id}")
    logger.info(f"   Post URL: {post_url}")
    logger.info("-" * 30)

    # --- SCRAPING CONDICIONAL DE CONTEXTO DEL POST ---
    post_context = ""
    if post_url and message:
        # Solo scrapear si el mensaje es genérico (no menciona programa específico)
        if apify_service.should_scrape_post(message):
            logger.info("Intentando extraer contexto del post de Facebook...")
            post_context = apify_service.scrape_facebook_post(post_url) or ""
            if post_context:
                logger.info(f"Contexto del post obtenido ({len(post_context)} caracteres)")
            else:
                logger.warning("No se pudo obtener contexto del post (continuando sin el)")
            logger.info("-" * 30)
        else:
            logger.info("Mensaje especifico - No se requiere scraping del post")
            logger.info("-" * 30)

    # --- AGENTE INTELIGENTE (COMENTARIOS) ---
    ai_response_text = None
    if message and contact_id:
        logger.info("Consultando Agente de Comentarios (Respuestas Cortas)...")
        
        # Invocar al Agente de Comentarios (optimizado para respuestas breves)
        initial_state = {
            "messages": [HumanMessage(content=message)],
            "contact_id": contact_id,
            "user_name": full_name or "Usuario",
            "post_context": post_context  # Añadir contexto del post
        }
        
        try:
            result = comment_agent.invoke(initial_state)  # Usar comment_agent
            ai_response = result["messages"][-1]
            structured_response = result.get("structured_response")
            
            # Con Pydantic structured output, el contenido SIEMPRE es un string
            ai_response_text = str(ai_response.content)
            
            logger.info(f"Respuesta IA (Comentario): {ai_response_text}")
            logger.info(f"Consulta Relevante: {structured_response.is_relevant_query if structured_response else 'N/A'}")

            # Solo enviar mensaje si es una consulta relevante
            if structured_response and structured_response.is_relevant_query:
                logger.info(f"Consulta relevante detectada -> Activando bandera y enviando DM...")

                # 1. Actualizar bandera para marcar en GHL que fue relevante (ACTIVATE)
                ghl_service.update_contact_field(
                    contact_id=contact_id,
                    field_key="response_content_facebook",
                    value="activate",
                    location_id=location_id
                )
                logger.info(f"Bandera 'response_content_facebook' ACTIVADA")

                # 2. Enviar la respuesta de la IA directamente por DM
                # Usamos send_message a través de GHL Service
                ghl_service.send_message(
                    contact_id=contact_id,
                    message=ai_response_text,
                    message_type="Facebook",
                    location_id=location_id
                )
                logger.info(f"DM enviado con respuesta IA: {ai_response_text[:50]}...")

            else:
                logger.info(f"Consulta no relevante -> Desactivando bandera")
                # Marcar bandera como DEACTIVATE para control interno
                ghl_service.update_contact_field(
                    contact_id=contact_id,
                    field_key="response_content_facebook", 
                    value="deactivate",
                    location_id=location_id
                )
            
        except Exception as e:
            logger.error(f"Error en Agente/Envio: {e}")


    # Retornamos los datos procesados para confirmar qué entendió el sistema
    return {
        "status": "success",
        "processed_data": {
            "full_name": full_name,
            "contact_id": contact_id,
            "message": message,
            "location_id": location_id,
            "post_metadata": {
                "page_id": page_id,
                "post_id": post_id,
                "post_url": post_url
            },
            "ai_response": ai_response_text
        }
    }

@router.post("/webhook_instagram")
async def receive_webhook_instagram(request: Request):
    """
    Webhook específico para COMENTARIOS DE INSTAGRAM.
    Recibe comentarios en posts/reels de Instagram, procesa con IA y actualiza campo personalizado.
    El Workflow de GHL se encarga de enviar la respuesta pública.
    """
    # Obtener el JSON crudo
    raw_body = await request.json()
    
    # Lógica de extracción robusta para comentarios de Instagram
    
    # 1. Mensaje (Instagram usa estructura diferente a Facebook)
    message = None
    # Intento A: triggerData (Estructura específica de IG Comment)
    message = get_nested_value(raw_body, ['triggerData', 'igCommentOnPost', 'ig', 'body'])
    # Intento B: customData
    if not message:
        message = get_nested_value(raw_body, ['customData', 'message_body'])
    # Intento C: Root
    if not message:
        message = raw_body.get('message_body')

    # 2. Location ID
    location_id = None
    location_id = get_nested_value(raw_body, ['location', 'id'])
    if not location_id:
        location_id = get_nested_value(raw_body, ['customData', 'location_id'])
    if not location_id:
        location_id = raw_body.get('location_id')

    # 3. Datos simples
    full_name = raw_body.get('full_name') or get_nested_value(raw_body, ['customData', 'full_name'])
    contact_id = raw_body.get('contact_id') or get_nested_value(raw_body, ['customData', 'contact_id'])
    phone = raw_body.get('phone') or get_nested_value(raw_body, ['customData', 'phone'])
    event_type = raw_body.get('event_type') or get_nested_value(raw_body, ['customData', 'event_type'])

    # 4. Metadatos del Post de Instagram (Si existen)
    page_id = get_nested_value(raw_body, ['triggerData', 'igCommentOnPost', 'ig', 'pageId'])
    post_id = get_nested_value(raw_body, ['triggerData', 'igCommentOnPost', 'ig', 'postId'])
    
    # La URL del post viene en un array 'postUrlOrId', primer elemento es la URL completa
    post_url_array = get_nested_value(raw_body, ['triggerData', 'igCommentOnPost', 'ig', 'postUrlOrId'])
    media_url = None
    if post_url_array and isinstance(post_url_array, list) and len(post_url_array) > 0:
        media_url = post_url_array[0]  # Primera URL del array
        logger.info(f"URL del post extraida de postUrlOrId: {media_url}")

    
    # Logs limpios con los datos finales encontrados
    logger.info("Webhook Instagram (Comentarios) Procesado:")
    logger.info(f"   Nombre: {full_name}")
    logger.info(f"   Contact ID: {contact_id}")
    logger.info(f"   Mensaje Recibido: {message}")
    logger.info(f"   Telefono: {phone}")
    logger.info(f"   Location ID: {location_id}")
    logger.info(f"   Tipo de Evento: {event_type}")
    logger.info(f"   Page ID: {page_id}")
    logger.info(f"   Post ID: {post_id}")
    logger.info(f"   Media URL: {media_url}")
    logger.info("-" * 30)

    # --- AGENTE INTELIGENTE (COMENTARIOS) ---
    ai_response_text = None
    if message and contact_id:
        logger.info("Consultando Agente de Comentarios Instagram (Respuestas Cortas)...")
        
        # --- SCRAPING INTELIGENTE DEL POST DE INSTAGRAM ---
        post_context = ""
        
        # Verificar si se debe scrapear el post (solo si el mensaje es genérico)
        if message and apify_service.should_scrape_post(message):
            if media_url:
                logger.info(f"Scrapeando post de Instagram: {media_url}")

                # Scrapear el post
                scraped_text = apify_service.scrape_instagram_post(media_url)
                if scraped_text:
                    post_context = f"\\n\\n▶ CONTEXTO DEL POST DE INSTAGRAM:\\n{scraped_text}"
                    logger.info(f"Caption scrapeado ({len(scraped_text)} chars)")
                else:
                    logger.warning("No se pudo scrapear el caption del post")
            else:
                logger.warning("No se encontro URL del post en el payload")


        
        # Invocar al Agente de Comentarios (mismo que Facebook, optimizado para respuestas breves)
        initial_state = {
            "messages": [HumanMessage(content=message)],
            "contact_id": contact_id,
            "user_name": full_name or "Usuario",
            "post_context": post_context
        }

        
        try:
            result = comment_agent.invoke(initial_state)  # Usar comment_agent
            ai_response = result["messages"][-1]
            structured_response = result.get("structured_response")
            
            # Con Pydantic structured output, el contenido SIEMPRE es un string
            ai_response_text = str(ai_response.content)
            
            logger.info(f"Respuesta IA (Comentario IG): {ai_response_text}")
            logger.info(f"Consulta Relevante: {structured_response.is_relevant_query if structured_response else 'N/A'}")

            # Solo enviar mensaje si es una consulta relevante
            if structured_response and structured_response.is_relevant_query:
                logger.info(f"Consulta relevante detectada (IG) -> Activando bandera y enviando DM...")

                # 1. Actualizar bandera para marcar en GHL que fue relevante (ACTIVATE)
                ghl_service.update_contact_field(
                    contact_id=contact_id,
                    field_key="response_content_instagram",
                    value="activate",
                    location_id=location_id
                )
                logger.info(f"Bandera 'response_content_instagram' ACTIVADA")

                # 2. Enviar respuesta IA directamente por DM
                ghl_service.send_message(
                    contact_id=contact_id,
                    message=ai_response_text,
                    message_type="IG",
                    location_id=location_id
                )
                logger.info(f"DM enviado con respuesta IA: {ai_response_text[:50]}...")

            else:
                logger.info(f"Consulta no relevante -> Desactivando bandera")
                ghl_service.update_contact_field(
                    contact_id=contact_id,
                    field_key="response_content_instagram", 
                    value="deactivate",
                    location_id=location_id
                )
            
        except Exception as e:
            logger.error(f"Error en Agente/Envio: {e}")


    # Retornamos los datos procesados para confirmar qué entendió el sistema
    return {
        "status": "success",
        "processed_data": {
            "full_name": full_name,
            "contact_id": contact_id,
            "message": message,
            "location_id": location_id,
            "post_metadata": {
                "page_id": page_id,
                "post_id": post_id,
                "media_url": media_url
            },
            "ai_response": ai_response_text
        }
    }
