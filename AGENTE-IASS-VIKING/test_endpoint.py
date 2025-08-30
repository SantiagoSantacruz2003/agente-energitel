#!/usr/bin/env python3
"""
Script para probar el endpoint /sendmensaje del agente IASS VIKING
"""

import json
import urllib.request
import urllib.parse
import uuid
import time

def test_sendmensaje_endpoint(base_url="http://localhost:8080"):
    """
    Prueba el endpoint /sendmensaje con diferentes escenarios
    """
    endpoint = f"{base_url}/sendmensaje"
    
    # Casos de prueba
    test_cases = [
        {
            "name": "Test básico - Asistente inicial",
            "data": {
                "api_key": "test-api-key",
                "message": "Hola, quiero hacer un pedido",
                "assistant": 0,
                "subscriber_id": "test-subscriber-001",
                "telefono": "+57300123456",
                "direccionCliente": "Calle 123 #45-67, Bogotá"
            }
        },
        {
            "name": "Test asistente domicilio",
            "data": {
                "api_key": "test-api-key", 
                "message": "Quiero que me lleven la comida a mi casa",
                "assistant": 1,
                "subscriber_id": "test-subscriber-002",
                "telefono": "+57301987654",
                "direccionCliente": "Carrera 15 #28-91, Medellín",
                "ai_provider": "llmo"
            }
        },
        {
            "name": "Test asistente forma de pago",
            "data": {
                "api_key": "test-api-key",
                "message": "¿Cómo puedo pagar?",
                "assistant": 3,
                "subscriber_id": "test-subscriber-003",
                "telefono": "+57312555888",
                "direccionCliente": "Avenida 7 #12-34, Cali"
            }
        }
    ]
    
    print("🧪 Iniciando pruebas del endpoint /sendmensaje\n")
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"📋 Test {i}: {test_case['name']}")
        print("-" * 50)
        
        try:
            # Preparar datos
            data = test_case['data']
            if 'thread_id' not in data:
                data['thread_id'] = f"thread_{uuid.uuid4()}"
            
            # Convertir a JSON
            json_data = json.dumps(data).encode('utf-8')
            
            # Crear request
            req = urllib.request.Request(
                endpoint,
                data=json_data,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'Test-Client/1.0'
                },
                method='POST'
            )
            
            # Enviar petición
            print(f"📤 Enviando petición a {endpoint}")
            print(f"📦 Datos: {json.dumps(data, indent=2)}")
            
            start_time = time.time()
            
            with urllib.request.urlopen(req, timeout=30) as response:
                response_time = time.time() - start_time
                status_code = response.getcode()
                response_data = response.read().decode('utf-8')
                
                print(f"✅ Status Code: {status_code}")
                print(f"⏱️ Response Time: {response_time:.2f}s")
                
                try:
                    parsed_response = json.loads(response_data)
                    print("📥 Response:")
                    print(json.dumps(parsed_response, indent=2, ensure_ascii=False))
                except json.JSONDecodeError:
                    print("📥 Response (raw):")
                    print(response_data)
                
        except urllib.error.HTTPError as e:
            print(f"❌ HTTP Error {e.code}: {e.reason}")
            try:
                error_response = e.read().decode('utf-8')
                error_data = json.loads(error_response)
                print("Error details:", json.dumps(error_data, indent=2))
            except:
                print("Error response:", error_response)
                
        except urllib.error.URLError as e:
            print(f"❌ URL Error: {e.reason}")
            
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
        
        print("\n" + "="*60 + "\n")
        time.sleep(1)  # Pausa entre tests

def test_server_connectivity(base_url="http://localhost:8080"):
    """
    Verifica si el servidor está corriendo
    """
    test_url = f"{base_url}/test"
    
    try:
        req = urllib.request.Request(test_url, method='GET')
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.getcode() == 200:
                print(f"✅ Servidor corriendo en {base_url}")
                print(f"🌐 Interfaz de prueba disponible en: {test_url}")
                return True
    except:
        pass
    
    print(f"❌ No se puede conectar al servidor en {base_url}")
    print("💡 Asegúrate de que el servidor esté corriendo:")
    print("   python3 test_app.py")
    return False

if __name__ == "__main__":
    import sys
    
    # Permitir URL personalizada
    base_url = "http://localhost:8080"
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    
    print("🚀 Test del Agente IASS VIKING - Endpoint /sendmensaje")
    print(f"🎯 Base URL: {base_url}")
    print("="*60)
    
    # Verificar conectividad
    if test_server_connectivity(base_url):
        print("\n")
        test_sendmensaje_endpoint(base_url)
    else:
        print("\n🔧 Para ejecutar las pruebas:")
        print("1. Ejecuta el servidor: python3 test_app.py")
        print("2. En otra terminal: python3 test_endpoint.py")
        print(f"3. O visita: {base_url}/test")