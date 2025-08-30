#!/usr/bin/env python3
"""
TEST DE FLUJO DE CONVERSACIÓN - MÚLTIPLES MENSAJES EN MISMO THREAD
Este script simula múltiples mensajes en el mismo thread para debuggear el problema
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

def send_message_to_thread(conversation_manager, thread_locks, thread_id, message, assistant_content, subscriber_id="test_user", llm_id="gpt-5"):
    """Envía un mensaje a un thread específico."""
    print(f"\n🔥 [MESSAGE {len(conversation_manager.get(thread_id).get('messages', [])) // 2 + 1}] Enviando: '{message}'")
    
    # Crear event para sincronización
    event = Event()
    
    # Llamar al handler
    thread = threading.Thread(
        target=generate_response_openai_mcp,
        args=(message, assistant_content, thread_id, event, subscriber_id, llm_id),
        kwargs={
            'conversation_manager': conversation_manager,
            'thread_locks': thread_locks,
            'mcp_servers': [],
            'assistant_number': 0
        }
    )
    
    thread.start()
    
    # Esperar por la respuesta
    success = event.wait(timeout=30)
    thread.join()
    
    if success:
        conversation = conversation_manager.get(thread_id)
        response = conversation.get("response", "") if conversation else ""
        print(f"✅ [RESPONSE] '{response}' (len: {len(response)})")
        return response
    else:
        print(f"❌ [TIMEOUT] No hubo respuesta en 30s")
        return None

def test_conversation_flow():
    """Test de flujo completo de conversación."""
    
    # Configurar variables de prueba
    test_assistant_content = "Eres un asistente útil y amigable. Responde de manera concisa y clara."
    test_thread_id = "conversation_test_456"
    
    print(f"🚀 [CONVERSATION TEST] Iniciando test de flujo de conversación")
    print(f"📋 [SETUP] Thread ID: {test_thread_id}")
    
    # Inicializar conversation manager
    conversation_manager = MemoryConversationManager({})
    thread_locks = {test_thread_id: threading.Lock()}
    
    # Crear conversación inicial
    conversation_manager.set(test_thread_id, {
        "status": "processing",
        "messages": [],
        "response": "",
    })
    
    print(f"✅ [SETUP] Conversación inicial creada")
    
    # MENSAJE 1
    print(f"\n" + "="*60)
    response1 = send_message_to_thread(
        conversation_manager, thread_locks, test_thread_id, 
        "Hola, ¿cómo estás?", test_assistant_content
    )
    
    if not response1:
        print(f"❌ [TEST FAILED] Mensaje 1 falló")
        return False
    
    # Mostrar estado del historial después del mensaje 1
    conv = conversation_manager.get(test_thread_id)
    messages = conv.get("messages", [])
    print(f"📚 [HISTORY 1] Historial tiene {len(messages)} mensajes")
    for i, msg in enumerate(messages):
        print(f"   {i+1}. {msg['role']}: '{msg['content'][:50]}...'")
    
    # MENSAJE 2
    print(f"\n" + "="*60)
    response2 = send_message_to_thread(
        conversation_manager, thread_locks, test_thread_id, 
        "¿Cuál es tu nombre?", test_assistant_content
    )
    
    if not response2:
        print(f"❌ [TEST FAILED] Mensaje 2 falló")
        return False
    
    # Mostrar estado del historial después del mensaje 2
    conv = conversation_manager.get(test_thread_id)
    messages = conv.get("messages", [])
    print(f"📚 [HISTORY 2] Historial tiene {len(messages)} mensajes")
    for i, msg in enumerate(messages):
        print(f"   {i+1}. {msg['role']}: '{msg['content'][:50]}...'")
    
    # MENSAJE 3
    print(f"\n" + "="*60)
    response3 = send_message_to_thread(
        conversation_manager, thread_locks, test_thread_id, 
        "¿Recuerdas mi primera pregunta?", test_assistant_content
    )
    
    if not response3:
        print(f"❌ [TEST FAILED] Mensaje 3 falló")
        return False
    
    # Mostrar estado final del historial
    conv = conversation_manager.get(test_thread_id)
    messages = conv.get("messages", [])
    print(f"📚 [HISTORY FINAL] Historial tiene {len(messages)} mensajes")
    for i, msg in enumerate(messages):
        print(f"   {i+1}. {msg['role']}: '{msg['content'][:50]}...'")
    
    print(f"\n🎉 [SUCCESS] Todas las respuestas funcionaron:")
    print(f"   1. '{response1}'")
    print(f"   2. '{response2}'") 
    print(f"   3. '{response3}'")
    
    return True

if __name__ == "__main__":
    print("🧪 INICIANDO TEST DE FLUJO DE CONVERSACIÓN")
    print("="*60)
    
    # Verificar que tenemos API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ ERROR: OPENAI_API_KEY no configurada en variables de entorno")
        sys.exit(1)
    
    print(f"✅ API Key encontrada: {api_key[:10]}...")
    
    success = test_conversation_flow()
    
    print("="*60)
    if success:
        print("🎉 TEST DE CONVERSACIÓN COMPLETADO EXITOSAMENTE")
    else:
        print("💥 TEST DE CONVERSACIÓN FALLÓ - Revisar logs")
    
    sys.exit(0 if success else 1)