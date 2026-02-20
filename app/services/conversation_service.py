import logging
from typing import List, Dict, Optional
from datetime import datetime
from app.services.supabase_client import get_supabase

logger = logging.getLogger(__name__)

class ConversationService:
    """
    Servicio para gestionar el historial de conversaciones usando Supabase.
    Mantiene contexto conversacional por contact_id.
    """

    def __init__(self):
        """Inicializa el cliente de Supabase."""
        self.client = get_supabase()
    
    def get_or_create_conversation(
        self, 
        contact_id: str, 
        location_id: str, 
        channel: str
    ) -> Optional[str]:
        """
        Busca una conversación existente por contact_id o crea una nueva.
        
        Args:
            contact_id: ID del contacto en GHL
            location_id: ID de la ubicación en GHL
            channel: Canal de comunicación (whatsapp, facebook, etc.)
        
        Returns:
            conversation_id (UUID) o None si hay error
        """
        if not self.client:
            logger.error("Supabase client not initialized")
            return None
        
        try:
            # Buscar conversación existente por contact_id
            response = self.client.table('conversations')\
                .select('*')\
                .eq('contact_id', contact_id)\
                .limit(1)\
                .execute()
            
            if response.data and len(response.data) > 0:
                # Conversación encontrada
                conversation_id = response.data[0]['id']
                logger.info(f"Conversación existente encontrada: {conversation_id}")
                return conversation_id
            else:
                # Crear nueva conversación
                new_conversation = self.client.table('conversations').insert({
                    'contact_id': contact_id,
                    'location_id': location_id,
                    'channel': channel,
                    'status': 'active'
                }).execute()
                
                conversation_id = new_conversation.data[0]['id']
                logger.info(f"Nueva conversación creada: {conversation_id}")
                return conversation_id
        
        except Exception as e:
            logger.error(f"Error en get_or_create_conversation: {e}")
            return None
    
    def save_message(
        self, 
        conversation_id: str, 
        role: str, 
        content: str,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Guarda un mensaje en la conversación.
        
        Args:
            conversation_id: UUID de la conversación
            role: 'user' o 'assistant'
            content: Contenido del mensaje
            metadata: Metadata adicional opcional
        
        Returns:
            True si se guardó exitosamente, False si hubo error
        """
        if not self.client:
            logger.error("Supabase client not initialized")
            return False

        if role not in ['user', 'assistant']:
            logger.error(f"Role inválido: {role}. Debe ser 'user' o 'assistant'")
            return False
        
        try:
            self.client.table('messages').insert({
                'conversation_id': conversation_id,
                'role': role,
                'content': content,
                'metadata': metadata
            }).execute()
            
            logger.info(f"Mensaje guardado: {role} - {len(content)} caracteres")
            return True
        
        except Exception as e:
            logger.error(f"Error guardando mensaje: {e}")
            return False
    
    def get_conversation_history(
        self, 
        contact_id: str, 
        limit: int = 20
    ) -> List[Dict]:
        """
        Obtiene el historial de mensajes de una conversación.
        
        Args:
            contact_id: ID del contacto en GHL
            limit: Número máximo de mensajes a retornar (default 20)
        
        Returns:
            Lista de diccionarios con {role, content, created_at}
            Retorna lista vacía si no hay conversación o hay error
        """
        if not self.client:
            logger.error("Supabase client not initialized")
            return []
        
        try:
            # Buscar conversación por contact_id
            conversation_response = self.client.table('conversations')\
                .select('id')\
                .eq('contact_id', contact_id)\
                .limit(1)\
                .execute()
            
            if not conversation_response.data or len(conversation_response.data) == 0:
                logger.info(f"No se encontró conversación para contact_id: {contact_id}")
                return []
            
            conversation_id = conversation_response.data[0]['id']
            
            # Obtener mensajes ordenados cronológicamente
            messages_response = self.client.table('messages')\
                .select('role, content, metadata, created_at')\
                .eq('conversation_id', conversation_id)\
                .order('created_at', desc=False)\
                .limit(limit)\
                .execute()
            
            messages = messages_response.data or []
            logger.info(f"Historial cargado: {len(messages)} mensajes")
            return messages
        
        except Exception as e:
            logger.error(f"Error obteniendo historial: {e}")
            return []
    
    def close_conversation(self, contact_id: str) -> bool:
        """
        Marca una conversación como cerrada.
        
        Args:
            contact_id: ID del contacto en GHL
        
        Returns:
            True si se cerró exitosamente, False si hubo error
        """
        if not self.client:
            logger.error("Supabase client not initialized")
            return False

        try:
            self.client.table('conversations')\
                .update({'status': 'closed'})\
                .eq('contact_id', contact_id)\
                .execute()

            logger.info(f"Conversación cerrada para contact_id: {contact_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error cerrando conversación: {e}")
            return False
    
    def migrate_conversation(
        self, 
        old_contact_id: str, 
        new_contact_id: str, 
        new_location_id: str
    ) -> bool:
        """
        Migra una conversación de un contact_id a otro.
        Útil cuando se transfiere un contacto a otro campus.
        
        Args:
            old_contact_id: ID del contacto original
            new_contact_id: ID del nuevo contacto (en el campus destino)
            new_location_id: ID de la nueva ubicación
        
        Returns:
            True si se migró exitosamente, False si hubo error
        """
        if not self.client:
            logger.error("Supabase client not initialized")
            return False

        try:
            # Buscar conversación del contacto original
            conversation_response = self.client.table('conversations')\
                .select('id')\
                .eq('contact_id', old_contact_id)\
                .limit(1)\
                .execute()
            
            if not conversation_response.data or len(conversation_response.data) == 0:
                logger.info(f"No hay conversación para migrar de contact_id: {old_contact_id}")
                return False
            
            conversation_id = conversation_response.data[0]['id']
            
            # Actualizar el contact_id y location_id de la conversación
            self.client.table('conversations')\
                .update({
                    'contact_id': new_contact_id,
                    'location_id': new_location_id
                })\
                .eq('id', conversation_id)\
                .execute()
            
            logger.info(f"Conversación migrada: {old_contact_id} → {new_contact_id}")
            return True
        except Exception as e:
            logger.error(f"Error migrando conversación: {e}")
            return False

    def is_message_exists(self, conversation_id: str, content: str, role: str = "assistant") -> bool:
        """
        Verifica si un mensaje específico ya existe en la BD.
        Usado para distinguir mensajes del Bot vs Humanos en GHL.

        Uses exact match first, then partial match (first 40 chars) as fallback
        to handle cases where GHL slightly modifies message content.

        Args:
            conversation_id: ID de conversación de GHL (se ignora para búsqueda global por contenido)
            content: Contenido del mensaje a buscar
            role: Rol del mensaje

        Returns:
            True si el mensaje existe (fue enviado por el bot)
        """
        if not self.client:
            return False

        try:
            # Limpiar contenido (strip zero-width spaces that GHL might add/remove)
            clean_content = content.replace('\u200B', '').strip()
            if not clean_content:
                return False

            # 1) Exact match
            response = self.client.table('messages')\
                .select('id')\
                .eq('role', role)\
                .eq('content', clean_content)\
                .limit(1)\
                .execute()

            if len(response.data) > 0:
                return True

            # 2) Partial match fallback: first 40 chars
            # Handles GHL truncating or modifying message content
            if len(clean_content) >= 40:
                prefix = clean_content[:40].replace('%', '\\%').replace('_', '\\_')
                response = self.client.table('messages')\
                    .select('id')\
                    .eq('role', role)\
                    .ilike('content', f'{prefix}%')\
                    .limit(1)\
                    .execute()

                if len(response.data) > 0:
                    logger.info("is_message_exists: coincidencia parcial encontrada (primeros 40 chars)")
                    return True

            return False

        except Exception as e:
            logger.warning(f"Error checking message existence: {e}")
            return False

    def set_human_active(self, contact_id: str, active: bool = True) -> bool:
        """
        Marca una conversación como tomada por un humano.
        Guarda el timestamp para auto-reset después de 24h.
        
        Args:
            contact_id: ID del contacto en GHL
            active: True para activar, False para desactivar
        """
        if not self.client:
            return False
        
        try:
            update_data = {
                'is_human_active': active
            }
            if active:
                update_data['human_takeover_at'] = datetime.utcnow().isoformat()
            else:
                update_data['human_takeover_at'] = None
            
            self.client.table('conversations')\
                .update(update_data)\
                .eq('contact_id', contact_id)\
                .execute()
            
            status = "ACTIVADO" if active else "DESACTIVADO"
            logger.info(f"Human Takeover {status} para contact_id: {contact_id}")
            return True
        except Exception as e:
            logger.warning(f"Error en set_human_active: {e}")
            return False

    def check_human_active(self, contact_id: str) -> bool:
        """
        Verifica si un humano tiene control de la conversación.
        Una vez activado, el bot se calla PERMANENTEMENTE.
        Solo se puede reactivar manualmente con reset_human_active().
        
        Returns:
            True si un humano está activo (bot debe callarse)
        """
        if not self.client:
            return False
        
        try:
            response = self.client.table('conversations')\
                .select('is_human_active')\
                .eq('contact_id', contact_id)\
                .limit(1)\
                .execute()
            
            if not response.data or len(response.data) == 0:
                return False
            
            is_active = response.data[0].get('is_human_active', False)
            
            if is_active:
                logger.info(f"Human Takeover ACTIVO (permanente) para contact_id: {contact_id}")
            
            return is_active
        
        except Exception as e:
            logger.warning(f"Error en check_human_active: {e}")
            return False

    def reset_human_active(self, contact_id: str) -> bool:
        """Desactiva el flag de human takeover (devuelve control al bot)."""
        return self.set_human_active(contact_id, False)
