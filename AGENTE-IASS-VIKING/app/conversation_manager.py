"""
Conversation Manager - Sistema de gestión de conversaciones con soporte Redis y Memory
Implementa patrón Strategy para alternar entre almacenamiento Redis y memoria.
"""

import json
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
import os

logger = logging.getLogger(__name__)

class ConversationManager(ABC):
    """Interfaz abstracta para gestión de conversaciones"""
    
    @abstractmethod
    def get(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene una conversación por thread_id"""
        pass
    
    @abstractmethod
    def set(self, thread_id: str, data: Dict[str, Any]) -> bool:
        """Crea/actualiza una conversación completa"""
        pass
    
    @abstractmethod
    def update(self, thread_id: str, updates: Dict[str, Any]) -> bool:
        """Actualiza campos específicos de una conversación"""
        pass
    
    @abstractmethod
    def delete(self, thread_id: str) -> bool:
        """Elimina una conversación"""
        pass
    
    @abstractmethod
    def exists(self, thread_id: str) -> bool:
        """Verifica si existe una conversación"""
        pass
    
    @abstractmethod
    def get_all_thread_ids(self) -> list:
        """Obtiene todos los thread_ids disponibles (para cleanup)"""
        pass
    
    @abstractmethod
    def cleanup_expired(self, expiration_seconds: int) -> int:
        """Limpia conversaciones expiradas, retorna cantidad eliminada"""
        pass


class MemoryConversationManager(ConversationManager):
    """Implementación en memoria - comportamiento actual"""
    
    def __init__(self, conversations_dict: Dict[str, Dict[str, Any]]):
        """
        Args:
            conversations_dict: Diccionario de conversaciones existente
        """
        self.conversations = conversations_dict
        logger.info("MemoryConversationManager inicializado")
    
    def get(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene conversación de memoria"""
        return self.conversations.get(thread_id)
    
    def set(self, thread_id: str, data: Dict[str, Any]) -> bool:
        """Establece conversación en memoria"""
        try:
            # Agregar timestamp de última actividad
            data["last_activity"] = time.time()
            self.conversations[thread_id] = data
            logger.debug(f"Conversación establecida en memoria: {thread_id}")
            return True
        except Exception as e:
            logger.error(f"Error al establecer conversación {thread_id}: {e}")
            return False
    
    def update(self, thread_id: str, updates: Dict[str, Any]) -> bool:
        """Actualiza campos específicos en memoria"""
        try:
            if thread_id not in self.conversations:
                logger.warning(f"Conversación {thread_id} no existe para actualizar")
                return False
            
            # Actualizar campos
            self.conversations[thread_id].update(updates)
            # Renovar timestamp
            self.conversations[thread_id]["last_activity"] = time.time()
            
            logger.debug(f"Conversación actualizada en memoria: {thread_id}")
            return True
        except Exception as e:
            logger.error(f"Error al actualizar conversación {thread_id}: {e}")
            return False
    
    def delete(self, thread_id: str) -> bool:
        """Elimina conversación de memoria"""
        try:
            if thread_id in self.conversations:
                del self.conversations[thread_id]
                logger.debug(f"Conversación eliminada de memoria: {thread_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error al eliminar conversación {thread_id}: {e}")
            return False
    
    def exists(self, thread_id: str) -> bool:
        """Verifica existencia en memoria"""
        return thread_id in self.conversations
    
    def get_all_thread_ids(self) -> list:
        """Obtiene todos los thread_ids de memoria"""
        return list(self.conversations.keys())
    
    def cleanup_expired(self, expiration_seconds: int) -> int:
        """Limpia conversaciones expiradas de memoria"""
        current_time = time.time()
        thread_ids = list(self.conversations.keys())
        cleaned = 0
        
        for thread_id in thread_ids:
            conversation = self.conversations.get(thread_id, {})
            last_activity = conversation.get("last_activity", 0)
            
            if current_time - last_activity > expiration_seconds:
                try:
                    del self.conversations[thread_id]
                    cleaned += 1
                    logger.info(f"Conversación expirada eliminada de memoria: {thread_id}")
                except Exception as e:
                    logger.error(f"Error al limpiar conversación {thread_id}: {e}")
        
        return cleaned


class RedisConversationManager(ConversationManager):
    """Implementación Redis con TTL automático y serialización JSON"""
    
    def __init__(self, redis_config: Dict[str, Any]):
        """
        Args:
            redis_config: Configuración Redis (host, port, db, password, etc.)
        """
        try:
            import redis
            
            logger.info(f"Intentando conectar a Redis con configuración: {redis_config}")
            
            # Configurar conexión Redis - priorizar REDIS_URL
            if 'url' in redis_config:
                # Usar REDIS_URL directamente (más simple para proveedores externos)
                self.redis_client = redis.from_url(
                    redis_config['url'],
                    decode_responses=True,  # Para manejar strings directamente
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True
                )
                logger.info(f"Conectando usando REDIS_URL: {redis_config['url'][:20]}...")
            else:
                # Usar configuración individual
                self.redis_client = redis.Redis(
                    host=redis_config.get('host', 'localhost'),
                    port=redis_config.get('port', 6379),
                    db=redis_config.get('db', 0),
                    password=redis_config.get('password', None),
                    decode_responses=True,  # Para manejar strings directamente
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    max_connections=redis_config.get('pool_size', 10)
                )
                logger.info(f"Conectando usando host/port: {redis_config.get('host', 'localhost')}:{redis_config.get('port', 6379)}")
            
            # Test de conexión
            logger.info("Probando conexión Redis...")
            ping_result = self.redis_client.ping()
            logger.info(f"Redis ping exitoso: {ping_result}")
            
            self.ttl_seconds = redis_config.get('ttl_seconds', 7200)  # 2 horas por defecto
            self.key_prefix = "conversation"
            
            logger.info(f"RedisConversationManager inicializado exitosamente - TTL: {self.ttl_seconds}s")
            
        except ImportError:
            logger.error("Redis no está instalado. Instala con: pip install redis")
            raise
        except Exception as e:
            logger.error(f"Error al conectar con Redis: {e}")
            raise
    
    def _get_key(self, thread_id: str) -> str:
        """Genera clave Redis para thread_id"""
        return f"{self.key_prefix}:{thread_id}"
    
    def _serialize_value(self, value: Any) -> str:
        """Serializa valores complejos a JSON"""
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)
    
    def _deserialize_value(self, value: str, original_type: type = None) -> Any:
        """Deserializa valores desde JSON"""
        if not value:
            return None
            
        # Intentar deserializar como JSON
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            # Si no es JSON válido, devolver como string
            return value
    
    def get(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene conversación de Redis"""
        try:
            key = self._get_key(thread_id)
            raw_data = self.redis_client.hgetall(key)
            
            if not raw_data:
                return None
            
            # Deserializar datos
            conversation = {}
            for field, value in raw_data.items():
                if field in ['messages', 'usage']:  # Campos que son objetos/arrays
                    conversation[field] = self._deserialize_value(value)
                elif field in ['assistant', 'thinking']:  # Campos numéricos
                    try:
                        conversation[field] = int(value)
                    except (ValueError, TypeError):
                        conversation[field] = value
                elif field == 'last_activity':  # Timestamp
                    try:
                        conversation[field] = float(value)
                    except (ValueError, TypeError):
                        conversation[field] = time.time()
                else:
                    conversation[field] = value
            
            logger.debug(f"Conversación obtenida de Redis: {thread_id}")
            return conversation
            
        except Exception as e:
            logger.error(f"Error al obtener conversación {thread_id} de Redis: {e}")
            return None
    
    def set(self, thread_id: str, data: Dict[str, Any]) -> bool:
        """Establece conversación en Redis con TTL"""
        try:
            key = self._get_key(thread_id)
            
            # Agregar timestamp si no existe
            if "last_activity" not in data:
                data["last_activity"] = time.time()
            
            # Serializar datos para Redis
            redis_data = {}
            for field, value in data.items():
                redis_data[field] = self._serialize_value(value)
            
            # Usar pipeline para atomicidad
            pipe = self.redis_client.pipeline()
            pipe.delete(key)  # Limpiar datos previos
            pipe.hset(key, mapping=redis_data)
            pipe.expire(key, self.ttl_seconds)
            pipe.execute()
            
            logger.debug(f"Conversación establecida en Redis: {thread_id} (TTL: {self.ttl_seconds}s)")
            return True
            
        except Exception as e:
            logger.error(f"Error al establecer conversación {thread_id} en Redis: {e}")
            return False
    
    def update(self, thread_id: str, updates: Dict[str, Any]) -> bool:
        """Actualiza campos específicos en Redis"""
        try:
            key = self._get_key(thread_id)
            
            # Verificar que la clave existe
            if not self.redis_client.exists(key):
                logger.warning(f"Conversación {thread_id} no existe en Redis para actualizar")
                return False
            
            # Preparar actualizaciones
            redis_updates = {}
            for field, value in updates.items():
                redis_updates[field] = self._serialize_value(value)
            
            # Siempre actualizar timestamp
            redis_updates["last_activity"] = str(time.time())
            
            # Usar pipeline para atomicidad
            pipe = self.redis_client.pipeline()
            pipe.hset(key, mapping=redis_updates)
            pipe.expire(key, self.ttl_seconds)  # Renovar TTL
            pipe.execute()
            
            logger.debug(f"Conversación actualizada en Redis: {thread_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error al actualizar conversación {thread_id} en Redis: {e}")
            return False
    
    def delete(self, thread_id: str) -> bool:
        """Elimina conversación de Redis"""
        try:
            key = self._get_key(thread_id)
            deleted = self.redis_client.delete(key)
            
            if deleted:
                logger.debug(f"Conversación eliminada de Redis: {thread_id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error al eliminar conversación {thread_id} de Redis: {e}")
            return False
    
    def exists(self, thread_id: str) -> bool:
        """Verifica existencia en Redis"""
        try:
            key = self._get_key(thread_id)
            return bool(self.redis_client.exists(key))
        except Exception as e:
            logger.error(f"Error al verificar existencia de {thread_id} en Redis: {e}")
            return False
    
    def get_all_thread_ids(self) -> list:
        """Obtiene todos los thread_ids de Redis"""
        try:
            pattern = f"{self.key_prefix}:*"
            keys = self.redis_client.keys(pattern)
            
            # Extraer thread_ids de las claves
            thread_ids = []
            for key in keys:
                thread_id = key.replace(f"{self.key_prefix}:", "")
                thread_ids.append(thread_id)
            
            return thread_ids
            
        except Exception as e:
            logger.error(f"Error al obtener thread_ids de Redis: {e}")
            return []
    
    def cleanup_expired(self, expiration_seconds: int) -> int:
        """Limpia conversaciones expiradas de Redis (backup del TTL nativo)"""
        try:
            current_time = time.time()
            thread_ids = self.get_all_thread_ids()
            cleaned = 0
            
            for thread_id in thread_ids:
                conversation = self.get(thread_id)
                if not conversation:
                    continue
                
                last_activity = conversation.get("last_activity", 0)
                
                # Verificar si está expirada manualmente (backup del TTL)
                if current_time - last_activity > expiration_seconds:
                    if self.delete(thread_id):
                        cleaned += 1
                        logger.info(f"Conversación expirada eliminada de Redis: {thread_id}")
            
            return cleaned
            
        except Exception as e:
            logger.error(f"Error en cleanup manual de Redis: {e}")
            return 0


def create_conversation_manager(use_redis: bool = False, 
                              redis_config: Dict[str, Any] = None,
                              conversations_dict: Dict[str, Dict[str, Any]] = None) -> ConversationManager:
    """
    Factory para crear el ConversationManager apropiado
    
    Args:
        use_redis: Si usar Redis o memoria
        redis_config: Configuración Redis
        conversations_dict: Diccionario de conversaciones para modo memoria
    
    Returns:
        ConversationManager: Instancia apropiada del manager
    """
    if use_redis:
        if not redis_config:
            # Usar REDIS_URL directamente si está disponible
            redis_url = os.getenv('REDIS_URL', None)
            
            if redis_url:
                redis_config = {
                    'url': redis_url,
                    'ttl_seconds': 2 * 60 * 60  # 2 horas
                }
                logger.info(f"Usando REDIS_URL para conexión")
            else:
                # Fallback a variables individuales
                redis_host = os.getenv('REDIS_HOST', 'localhost')
                if redis_host.startswith('redis://'):
                    # Extraer componentes de la URL redis://default:password@host:port
                    import re
                    match = re.match(r'redis://(?:([^:]+):([^@]+)@)?([^:]+):(\d+)', redis_host)
                    if match:
                        username, password, host, port = match.groups()
                        redis_config = {
                            'host': host,
                            'port': int(port),
                            'db': int(os.getenv('REDIS_DB', 0)),
                            'password': password or os.getenv('REDIS_PASSWORD', None),
                            'pool_size': int(os.getenv('REDIS_CONNECTION_POOL_SIZE', 10)),
                            'ttl_seconds': 2 * 60 * 60  # 2 horas
                        }
                        logger.info(f"Parseada URL Redis - Host: {host}, Port: {port}, Password: {'***' if password else 'None'}")
                    else:
                        logger.error(f"No se pudo parsear REDIS_HOST: {redis_host}")
                        redis_config = {
                            'host': 'localhost',
                            'port': int(os.getenv('REDIS_PORT', 6379)),
                            'db': int(os.getenv('REDIS_DB', 0)),
                            'password': os.getenv('REDIS_PASSWORD', None),
                            'pool_size': int(os.getenv('REDIS_CONNECTION_POOL_SIZE', 10)),
                            'ttl_seconds': 2 * 60 * 60  # 2 horas
                        }
                else:
                    redis_config = {
                        'host': redis_host,
                        'port': int(os.getenv('REDIS_PORT', 6379)),
                        'db': int(os.getenv('REDIS_DB', 0)),
                        'password': os.getenv('REDIS_PASSWORD', None),
                        'pool_size': int(os.getenv('REDIS_CONNECTION_POOL_SIZE', 10)),
                        'ttl_seconds': 2 * 60 * 60  # 2 horas
                    }
        
        try:
            return RedisConversationManager(redis_config)
        except Exception as e:
            logger.error(f"Falló inicialización Redis, fallback a memoria: {e}")
            # Fallback a memoria si Redis falla
            return MemoryConversationManager(conversations_dict or {})
    else:
        return MemoryConversationManager(conversations_dict or {})