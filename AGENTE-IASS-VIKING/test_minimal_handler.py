#!/usr/bin/env python3
"""
TEST SCRIPT PARA EL HANDLER MÍNIMO SIMPLIFICADO
Este script simula una llamada al handler OpenAI para debuggear el problema de respuestas vacías
"""

import os
import sys
import time
import threading
import logging
from threading import Event
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# Configurar logging para ver todos los detalles
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Importar los módulos necesarios
from app.conversation_manager import MemoryConversationManager
from app.openai_responses_handler import generate_response_openai_mcp

def test_minimal_handler():
    """Test del handler mínimo OpenAI."""
    
    # Configurar variables de prueba
    test_message = "Hola, ¿cómo estás?"
    test_assistant_content = "Eres un asistente útil y amigable. Responde de manera concisa y clara."
    test_thread_id = "test_thread_123"
    test_subscriber_id = "test_user"
    test_llm_id = "gpt-5"  # Usar GPT-5 como default
    
    print(f"🧪 [TEST SETUP] Iniciando test con:")
    print(f"   - Message: {test_message}")
    print(f"   - Thread ID: {test_thread_id}")
    print(f"   - LLM ID: {test_llm_id}")
    print(f"   - Assistant content length: {len(test_assistant_content)}")
    
    # Inicializar conversation manager
    conversation_manager = MemoryConversationManager({})
    thread_locks = {test_thread_id: threading.Lock()}
    
    # Crear conversación inicial (como lo hace endpoints.py)
    conversation_manager.set(test_thread_id, {
        "status": "processing",
        "messages": [],
        "response": "",
    })
    
    print(f"🧪 [TEST SETUP] Conversación inicial creada")
    
    # Crear event para sincronización
    event = Event()
    
    # Llamar al handler en un hilo (como lo hace endpoints.py)
    print(f"🧪 [TEST EXECUTION] Iniciando handler...")
    
    thread = threading.Thread(
        target=generate_response_openai_mcp,
        args=(
            test_message,
            test_assistant_content,
            test_thread_id,
            event,
            test_subscriber_id,
            test_llm_id
        ),
        kwargs={
            'conversation_manager': conversation_manager,
            'thread_locks': thread_locks,
            'mcp_servers': [],  # Sin MCP servers para test mínimo
            'assistant_number': 0
        }
    )
    
    thread.start()
    
    # Esperar por la respuesta (timeout 30 segundos)
    print(f"🧪 [TEST EXECUTION] Esperando respuesta...")
    event_result = event.wait(timeout=30)
    
    if not event_result:
        print(f"❌ [TEST ERROR] TIMEOUT - El handler no completó en 30 segundos")
        return False
    
    thread.join()
    
    # Verificar resultado
    print(f"🧪 [TEST VERIFICATION] Verificando resultado...")
    final_conversation = conversation_manager.get(test_thread_id)
    
    if not final_conversation:
        print(f"❌ [TEST ERROR] Conversación no encontrada después del handler")
        return False
    
    response = final_conversation.get("response", "")
    status = final_conversation.get("status", "")
    messages = final_conversation.get("messages", [])
    
    print(f"🔍 [TEST RESULTS]")
    print(f"   - Status: {status}")
    print(f"   - Response length: {len(response)}")
    print(f"   - Response content: '{response}'")
    print(f"   - Messages count: {len(messages)}")
    print(f"   - Messages: {messages}")
    
    if not response:
        print(f"❌ [TEST FAILED] RESPUESTA VACÍA - Este es el problema que estamos debuggeando")
        return False
    elif status == "error":
        print(f"❌ [TEST FAILED] Handler reportó error: {response}")
        return False
    else:
        print(f"✅ [TEST SUCCESS] Handler completó exitosamente")
        return True

if __name__ == "__main__":
    print("🚀 INICIANDO TEST DEL HANDLER MÍNIMO OPENAI")
    print("="*60)
    
    # Verificar que tenemos API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ ERROR: OPENAI_API_KEY no configurada en variables de entorno")
        sys.exit(1)
    
    print(f"✅ API Key encontrada: {api_key[:10]}...")
    
    success = test_minimal_handler()
    
    print("="*60)
    if success:
        print("🎉 TEST COMPLETADO EXITOSAMENTE")
    else:
        print("💥 TEST FALLÓ - Revisar logs para detalles")
    
    sys.exit(0 if success else 1)