from flask import Flask
import logging
import threading
import os
from dotenv import load_dotenv
import time

from app.endpoints import init_endpoints
from app.cleanup import start_cleanup_thread
from app.conversation_manager import create_conversation_manager

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)

# Configuración del logging
logging.basicConfig(
    level=logging.INFO,  # Nivel de logging: DEBUG, INFO, WARNING, ERROR, CRITICAL
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()  # Salida a la consola
    ])


logger = logging.getLogger(__name__)

# Variables globales
conversations = {}  # Mantenido para compatibilidad con MemoryConversationManager
thread_locks = {}

# Configuración Redis
USE_REDIS = os.getenv('USE_REDIS', 'false').lower() == 'true'
REDIS_URL = os.getenv('REDIS_URL', None)
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

logger.info(f"Configuración Redis - USE_REDIS: {USE_REDIS}")
if REDIS_URL:
    logger.info(f"REDIS_URL: {REDIS_URL[:20]}... (usando URL directa)")
else:
    logger.info(f"REDIS_HOST: {REDIS_HOST}")
    logger.info(f"REDIS_PASSWORD: {'***' if REDIS_PASSWORD else 'None'}")

# Inicializar ConversationManager
logger.info(f"Inicializando ConversationManager - Redis: {USE_REDIS}")
try:
    conversation_manager = create_conversation_manager(
        use_redis=USE_REDIS,
        conversations_dict=conversations  # Para modo memoria
    )
    logger.info(f"ConversationManager inicializado exitosamente - Tipo: {type(conversation_manager).__name__}")
except Exception as e:
    logger.error(f"Error inicializando ConversationManager: {e}")
    # Fallback a modo memoria
    conversation_manager = create_conversation_manager(
        use_redis=False,
        conversations_dict=conversations
    )
    logger.warning("Fallback a MemoryConversationManager")





# Inicializar endpoints
init_endpoints(app, conversation_manager, thread_locks)

# Iniciar hilo de limpieza
start_cleanup_thread(conversation_manager, thread_locks)

if __name__ == '__main__':
    logger.info("Iniciando la aplicación Flask")
    port = int(os.getenv('PORT', 8080))  # Puerto dinámico para deployment
    app.run(host='0.0.0.0', port=port, debug=False)
