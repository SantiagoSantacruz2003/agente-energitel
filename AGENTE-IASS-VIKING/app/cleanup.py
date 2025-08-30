import time
import threading
import logging

logger = logging.getLogger(__name__)

def cleanup_inactive_conversations(conversation_manager, thread_locks):
    """Limpia conversaciones inactivas después de 2 horas."""
    expiration_time = 7200  # 2 horas en segundos (cambiado de 3h)
    
    try:
        # Usar el método cleanup_expired del manager
        cleaned_conversations = conversation_manager.cleanup_expired(expiration_time)
        
        # Limpiar locks huérfanos
        thread_ids = conversation_manager.get_all_thread_ids()
        valid_thread_ids = set(thread_ids)
        
        # Eliminar locks de threads que ya no existen
        locks_to_remove = []
        for thread_id in list(thread_locks.keys()):
            if thread_id not in valid_thread_ids:
                locks_to_remove.append(thread_id)
        
        cleaned_locks = 0
        for thread_id in locks_to_remove:
            try:
                del thread_locks[thread_id]
                cleaned_locks += 1
                logger.debug(f"Lock huérfano eliminado: {thread_id}")
            except Exception as e:
                logger.error(f"Error al eliminar lock {thread_id}: {e}")
        
        if cleaned_conversations > 0 or cleaned_locks > 0:
            logger.info(f"Limpieza completada - Conversaciones: {cleaned_conversations}, Locks: {cleaned_locks}")
        else:
            logger.debug("Limpieza ejecutada - No hay elementos para limpiar")
            
        return cleaned_conversations + cleaned_locks
        
    except Exception as e:
        logger.error(f"Error en cleanup_inactive_conversations: {e}")
        return 0

def start_cleanup_thread(conversation_manager, thread_locks):
    """Inicia un hilo que ejecuta la limpieza cada hora."""
    def cleanup_worker():
        while True:
            try:
                time.sleep(3600)  # Ejecutar cada hora
                logger.info("Ejecutando limpieza programada (2h expiration)")
                cleanup_inactive_conversations(conversation_manager, thread_locks)
            except Exception as e:
                logger.error(f"Error en hilo de limpieza: {e}")

    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()
    logger.info("Hilo de limpieza iniciado - TTL: 2 horas")