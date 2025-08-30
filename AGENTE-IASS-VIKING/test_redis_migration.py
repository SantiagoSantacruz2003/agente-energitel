#!/usr/bin/env python3
"""
Script de prueba para verificar la migración a Redis
Permite probar ambos modos: memoria y Redis
"""

import os
import sys
import time
import json
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.conversation_manager import create_conversation_manager

def test_memory_mode():
    """Prueba el modo memoria"""
    print("🧪 TESTING MEMORY MODE")
    print("=" * 50)
    
    # Crear manager en modo memoria
    conversations_dict = {}
    manager = create_conversation_manager(
        use_redis=False,
        conversations_dict=conversations_dict
    )
    
    # Test básico
    thread_id = "test_thread_123"
    test_data = {
        "status": "processing",
        "response": None,
        "messages": [{"role": "user", "content": "Hola"}],
        "assistant": 0,
        "thinking": 0,
        "telefono": "123456789",
        "direccionCliente": "Test Address",
        "usage": None
    }
    
    # Test set
    print(f"✅ Setting conversation: {manager.set(thread_id, test_data)}")
    
    # Test get
    retrieved = manager.get(thread_id)
    print(f"✅ Retrieved conversation: {retrieved is not None}")
    print(f"   Status: {retrieved.get('status') if retrieved else 'None'}")
    print(f"   Messages count: {len(retrieved.get('messages', [])) if retrieved else 0}")
    
    # Test update
    updates = {"status": "completed", "response": "Test response"}
    print(f"✅ Updating conversation: {manager.update(thread_id, updates)}")
    
    # Test exists
    print(f"✅ Conversation exists: {manager.exists(thread_id)}")
    
    # Test cleanup
    time.sleep(1)  # Para asegurar diferencia de timestamp
    cleaned = manager.cleanup_expired(0)  # 0 seconds = clean all
    print(f"✅ Cleanup test: {cleaned} conversations cleaned")
    
    # Test después de cleanup
    print(f"✅ Exists after cleanup: {manager.exists(thread_id)}")
    
    print("✅ Memory mode tests completed\n")

def test_redis_mode():
    """Prueba el modo Redis"""
    print("🧪 TESTING REDIS MODE")
    print("=" * 50)
    
    try:
        # Intentar crear manager en modo Redis
        manager = create_conversation_manager(use_redis=True)
        
        # Test básico
        thread_id = "test_redis_thread_456"
        test_data = {
            "status": "processing",
            "response": None,
            "messages": [{"role": "user", "content": "Hola Redis"}],
            "assistant": 1,
            "thinking": 1,
            "telefono": "987654321",
            "direccionCliente": "Redis Address",
            "usage": {"input_tokens": 10, "output_tokens": 20}
        }
        
        # Test set
        print(f"✅ Setting conversation: {manager.set(thread_id, test_data)}")
        
        # Test get
        retrieved = manager.get(thread_id)
        print(f"✅ Retrieved conversation: {retrieved is not None}")
        if retrieved:
            print(f"   Status: {retrieved.get('status')}")
            print(f"   Messages count: {len(retrieved.get('messages', []))}")
            print(f"   Usage: {retrieved.get('usage')}")
        
        # Test update
        updates = {"status": "completed", "response": "Redis response test"}
        print(f"✅ Updating conversation: {manager.update(thread_id, updates)}")
        
        # Verificar update
        updated = manager.get(thread_id)
        print(f"✅ Update verified: {updated.get('response') == 'Redis response test' if updated else False}")
        
        # Test exists
        print(f"✅ Conversation exists: {manager.exists(thread_id)}")
        
        # Test all thread IDs
        all_ids = manager.get_all_thread_ids()
        print(f"✅ Total conversations in Redis: {len(all_ids)}")
        print(f"   Thread IDs: {all_ids[:3]}{'...' if len(all_ids) > 3 else ''}")
        
        # Test TTL (TTL should be ~2 hours = 7200 seconds)
        print("✅ Testing TTL...")
        import redis
        try:
            r = redis.Redis(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                db=int(os.getenv('REDIS_DB', 0)),
                decode_responses=True
            )
            ttl = r.ttl(f"conversation:{thread_id}")
            print(f"   TTL remaining: {ttl} seconds (~{ttl/3600:.1f} hours)")
        except Exception as e:
            print(f"   TTL check failed: {e}")
        
        # Test cleanup
        time.sleep(1)
        cleaned = manager.cleanup_expired(0)  # Clean all
        print(f"✅ Cleanup test: {cleaned} conversations cleaned")
        
        # Test después de cleanup
        print(f"✅ Exists after cleanup: {manager.exists(thread_id)}")
        
        print("✅ Redis mode tests completed")
        
    except ImportError:
        print("❌ Redis no está instalado. Instala con: pip install redis")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print("   Verifica que Redis esté ejecutándose y la configuración sea correcta")

def test_environment_variables():
    """Prueba la configuración de variables de entorno"""
    print("🧪 TESTING ENVIRONMENT VARIABLES")
    print("=" * 50)
    
    env_vars = {
        'USE_REDIS': os.getenv('USE_REDIS', 'Not Set'),
        'REDIS_HOST': os.getenv('REDIS_HOST', 'Not Set'), 
        'REDIS_PORT': os.getenv('REDIS_PORT', 'Not Set'),
        'REDIS_DB': os.getenv('REDIS_DB', 'Not Set'),
        'REDIS_PASSWORD': os.getenv('REDIS_PASSWORD', 'Not Set'),
        'REDIS_CONNECTION_POOL_SIZE': os.getenv('REDIS_CONNECTION_POOL_SIZE', 'Not Set')
    }
    
    for var, value in env_vars.items():
        status = "✅" if value != "Not Set" else "⚠️"
        print(f"{status} {var}: {value}")
    
    print()

def main():
    """Función principal"""
    print("🚀 REDIS MIGRATION TEST SUITE")
    print("=" * 50)
    print()
    
    # Test environment
    test_environment_variables()
    
    # Test memory mode (always available)
    test_memory_mode()
    
    # Test Redis mode (if configured)
    use_redis = os.getenv('USE_REDIS', 'false').lower() == 'true'
    if use_redis:
        test_redis_mode()
    else:
        print("⚠️  Redis mode disabled (USE_REDIS=false)")
        print("   Para probar Redis: SET USE_REDIS=true en .env")
    
    print()
    print("🎉 Test suite completed!")

if __name__ == "__main__":
    main()