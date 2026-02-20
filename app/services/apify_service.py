import os
import logging
from typing import Optional
from apify_client import ApifyClient
from dotenv import load_dotenv
from app.services.llm_client import get_chat_model
from app.models.response_models import MessageAnalysis
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()

logger = logging.getLogger(__name__)

class ApifyService:
    """
    Servicio para interactuar con Apify API y realizar scraping de posts de Facebook.
    """
    
    def __init__(self):
        self.api_token = os.getenv("APIFY_API_TOKEN")
        if not self.api_token:
            logger.warning("APIFY_API_TOKEN not found in environment variables")
            self.client = None
        else:
            self.client = ApifyClient(self.api_token)
    
    def should_scrape_post(self, message: str) -> bool:
        """
        Usa el LLM para determinar inteligentemente si se debe scrapear el post.
        
        Retorna True si el mensaje es genérico y NO menciona un programa académico específico.
        Retorna False si el mensaje ya contiene información del programa académico.
        
        Args:
            message: Mensaje del usuario
            
        Returns:
            True si debe scrapear, False si no
        """
        if not message:
            return False
        
        try:
            # Prompt del sistema para análisis
            system_prompt = """Eres un analizador de mensajes para determinar si se necesita contexto adicional de un post de Facebook.

NIVELES EDUCATIVOS DISPONIBLES EN COLEGIO SAN ÁNGEL:
- Preescolar
- Primaria
- Secundaria
- Bachillerato

TU TAREA:
Analiza el mensaje del usuario y determina si necesitamos extraer el contexto del post de Facebook.

RETORNA needs_post_context = TRUE si:
- El mensaje es genérico pidiendo información ("info", "más información", "detalles", "costos", "ubicación", etc.)
- Y NO menciona un programa académico específico
- Ejemplo: "info" → TRUE (necesita saber de qué trata el post)
- Ejemplo: "más información" → TRUE
- Ejemplo: "costos" → TRUE

RETORNA needs_post_context = FALSE si:
- El mensaje YA menciona un nivel educativo específico
- Ejemplo: "info primaria" → FALSE (ya sabemos que pregunta por Primaria)
- Ejemplo: "quiero inscribir a mi hijo en secundaria" → FALSE (ya menciona Secundaria)
- Ejemplo: "bachillerato horarios" → FALSE (ya menciona Bachillerato)
- El mensaje no es una consulta académica
- Ejemplo: "hola" → FALSE
- Ejemplo: "gracias" → FALSE

IMPORTANTE: Sé estricto. Solo retorna TRUE cuando el mensaje sea una consulta genérica SIN programa específico."""

            # Invocar LLM con structured output
            model = get_chat_model(structured_output=MessageAnalysis)
            response: MessageAnalysis = model.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Mensaje del usuario: {message}")
            ])
            
            # Log de la decisión
            if response.needs_post_context:
                logger.info(f"LLM: Mensaje generico - Se scrapeara el post")
                logger.info(f"Razon: {response.reasoning}")
            else:
                logger.info(f"LLM: Mensaje especifico - No se necesita scraping")
                logger.info(f"Programa mencionado: {response.mentioned_program or 'Ninguno'}")
                logger.info(f"Razon: {response.reasoning}")
            
            return response.needs_post_context
            
        except Exception as e:
            logger.warning(f"Error al analizar mensaje con LLM: {e}")
            logger.warning(f"Fallback: No scrapear por seguridad")
            return False
    
    def scrape_facebook_post(self, post_url: str) -> Optional[str]:
        """
        Extrae el contenido/descripción de un post de Facebook.
        
        Args:
            post_url: URL del post de Facebook
            
        Returns:
            El texto del post extraído (máximo 500 caracteres), o None si falla
        """
        if not self.client:
            logger.error("Apify client not initialized (missing API token)")
            return None

        if not post_url:
            logger.warning("No post URL provided for scraping")
            return None

        try:
            logger.info(f"Scraping Facebook post: {post_url}")
            
            # Usar el actor especializado de Facebook Posts Scraper (ID directo)
            actor_call = self.client.actor("KoJrdxJCTtpon81KY").call(
                run_input={
                    "startUrls": [{"url": post_url}],
                    "resultsLimit": 1,
                    "captionText": True  # Activado para obtener texto completo
                }
            )
            
            # Obtener los resultados
            dataset_items = list(self.client.dataset(actor_call["defaultDatasetId"]).iterate_items())
            
            if dataset_items and len(dataset_items) > 0:
                result = dataset_items[0]
                
                # DEBUG: Log all fields to see where the full text is
                logger.debug(f"DEBUG - Campos del resultado:")
                for key, value in result.items():
                    if isinstance(value, str) and len(value) > 50:
                        logger.debug(f"   {key}: {value[:200]}...")
                    elif isinstance(value, (list, dict)) and value:
                        logger.debug(f"   {key}: {type(value).__name__} con {len(value) if isinstance(value, (list, dict)) else 0} elementos")
                    else:
                        logger.debug(f"   {key}: {value}")
                
                # El actor de Facebook separa el contenido en diferentes campos
                # Combinar: text + link + textReferences
                text_parts = []
                
                # 1. Texto principal
                main_text = result.get('text', '').strip()
                if main_text:
                    text_parts.append(main_text)
                
                # 2. Link (WhatsApp, etc.)
                link = result.get('link', '').strip()
                if link:
                    text_parts.append(f"📲 {link}")
                
                # 3. TextReferences (contiene teléfonos, ubicación, etc.)
                text_refs = result.get('textReferences', [])
                if isinstance(text_refs, list):
                    for ref in text_refs:
                        if isinstance(ref, dict):
                            # Puede tener 'text', 'title', 'description', etc.
                            for key in ['text', 'title', 'description', 'subtitle']:
                                ref_value = ref.get(key, '')
                                if ref_value and isinstance(ref_value, str) and ref_value.strip():
                                    text_parts.append(ref_value.strip())
                
                # Combinar sin duplicados
                post_text = "\n".join(dict.fromkeys(text_parts))  # Elimina duplicados manteniendo orden
                
                if post_text and len(post_text) > 20:
                    logger.info(f"Post scrapeado exitosamente ({len(post_text)} caracteres)")
                    logger.info(f"Contenido completo: {post_text}")
                    
                    # Limitar el tamaño para no sobrecargar el prompt (aumentado a 1500)
                    max_length = 1500
                    if len(post_text) > max_length:
                        post_text = post_text[:max_length] + "..."
                        logger.info(f"Descripcion del post truncada a {max_length} caracteres")
                    return post_text
                else:
                    logger.warning("No se pudo extraer texto del post")
                    return None
            else:
                logger.warning("No se obtuvieron resultados del scraping")
                return None

        except Exception as e:
            logger.error(f"Error al scrapear post de Facebook: {e}")
            return None
    
    def scrape_instagram_post(self, post_url: str) -> Optional[str]:
        """
        Extrae el contenido/descripción de un post de Instagram.
        
        Args:
            post_url: URL del post de Instagram
            
        Returns:
            El texto del post extraído (caption/descripción), o None si falla
        """
        if not self.client:
            logger.error("Apify client not initialized (missing API token)")
            return None

        if not post_url:
            logger.warning("No post URL provided for scraping")
            return None

        try:
            logger.info(f"Scraping Instagram post: {post_url}")
            
            # Usar Instagram Scraper que acepta URLs directas
            # Actor ID: shu8hvrXbJbY3Eb9W (Instagram Scraper by Apify)
            actor_call = self.client.actor("shu8hvrXbJbY3Eb9W").call(
                run_input={
                    "directUrls": [post_url],
                    "resultsType": "posts",
                    "resultsLimit": 1,
                    "addParentData": False
                }
            )


            
            # Obtener los resultados
            dataset_items = list(self.client.dataset(actor_call["defaultDatasetId"]).iterate_items())
            
            if dataset_items and len(dataset_items) > 0:
                result = dataset_items[0]
                
                # DEBUG: Log available fields
                logger.debug(f"DEBUG - Campos del resultado Instagram:")
                for key, value in result.items():
                    if isinstance(value, str) and len(value) > 50:
                        logger.debug(f"   {key}: {value[:200]}...")
                    elif isinstance(value, (list, dict)) and value:
                        logger.debug(f"   {key}: {type(value).__name__} con {len(value) if isinstance(value, (list, dict)) else 0} elementos")
                    else:
                        logger.debug(f"   {key}: {value}")
                
                # Instagram guarda el texto en 'caption'
                post_text = result.get('caption', '').strip()
                
                # También puede tener otros campos útiles
                if not post_text:
                    # Intentar con otros campos alternativos
                    post_text = result.get('text', '').strip()
                
                if post_text and len(post_text) > 20:
                    logger.info(f"Post de Instagram scrapeado exitosamente ({len(post_text)} caracteres)")
                    logger.info(f"Caption: {post_text}")
                    
                    # Limitar el tamaño para no sobrecargar el prompt
                    max_length = 1500
                    if len(post_text) > max_length:
                        post_text = post_text[:max_length] + "..."
                        logger.info(f"Caption truncado a {max_length} caracteres")
                    return post_text
                else:
                    logger.warning("No se pudo extraer caption del post de Instagram")
                    return None
            else:
                logger.warning("No se obtuvieron resultados del scraping de Instagram")
                return None

        except Exception as e:
            logger.error(f"Error al scrapear post de Instagram: {e}")
            return None
