#!/usr/bin/env python3
"""
Script de prueba simplificado para el endpoint /sendmensaje
Sin dependencias externas - solo usando bibliotecas estándar de Python
"""

import json
import http.server
import socketserver
from urllib.parse import urlparse, parse_qs
import threading
import time
from datetime import datetime

class TestHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/sendmensaje':
            self.handle_sendmensaje()
        else:
            self.send_error(404, "Endpoint not found")
    
    def do_GET(self):
        if self.path.startswith('/test'):
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            test_form = '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Test Agente IASS Viking</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; }
                    .container { max-width: 600px; margin: 0 auto; }
                    .form-group { margin: 10px 0; }
                    label { display: block; margin-bottom: 5px; }
                    input, textarea, select { width: 100%; padding: 8px; }
                    button { padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; }
                    button:hover { background: #0056b3; }
                    .response { margin-top: 20px; padding: 10px; background: #f8f9fa; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Test Endpoint /sendmensaje</h1>
                    <form id="testForm">
                        <div class="form-group">
                            <label>API Key:</label>
                            <input type="text" id="api_key" placeholder="test-api-key" value="test-api-key">
                        </div>
                        <div class="form-group">
                            <label>Message:</label>
                            <textarea id="message" placeholder="Hola, quiero hacer un pedido">Hola, quiero hacer un pedido</textarea>
                        </div>
                        <div class="form-group">
                            <label>Assistant:</label>
                            <select id="assistant">
                                <option value="0">Inicial (0)</option>
                                <option value="1">Domicilio (1)</option>
                                <option value="2">Recoger (2)</option>
                                <option value="3">Forma Pago (3)</option>
                                <option value="4">Postventa (4)</option>
                                <option value="5">Fuera Horario (5)</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Thread ID:</label>
                            <input type="text" id="thread_id" placeholder="Auto-generated" value="">
                        </div>
                        <div class="form-group">
                            <label>Subscriber ID:</label>
                            <input type="text" id="subscriber_id" placeholder="test-subscriber" value="test-subscriber">
                        </div>
                        <div class="form-group">
                            <label>Model ID:</label>
                            <select id="ai_provider">
                                <option value="">Anthropic (default)</option>
                                <option value="llmo">OpenAI</option>
                                <option value="llmg">Gemini</option>
                                <option value="deepseek">DeepSeek</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Telefono:</label>
                            <input type="text" id="telefono" placeholder="+57300123456" value="+57300123456">
                        </div>
                        <div class="form-group">
                            <label>Dirección Cliente:</label>
                            <input type="text" id="direccionCliente" placeholder="Calle 123 #45-67" value="Calle 123 #45-67">
                        </div>
                        <button type="submit">Test Endpoint</button>
                    </form>
                    <div id="response" class="response" style="display:none;">
                        <h3>Response:</h3>
                        <pre id="responseContent"></pre>
                    </div>
                </div>
                
                <script>
                document.getElementById('testForm').addEventListener('submit', async function(e) {
                    e.preventDefault();
                    
                    const data = {
                        api_key: document.getElementById('api_key').value,
                        message: document.getElementById('message').value,
                        assistant: parseInt(document.getElementById('assistant').value),
                        thread_id: document.getElementById('thread_id').value || undefined,
                        subscriber_id: document.getElementById('subscriber_id').value,
                        ai_provider: document.getElementById('ai_provider').value,
                        telefono: document.getElementById('telefono').value,
                        direccionCliente: document.getElementById('direccionCliente').value,
                        thinking: 0,
                        use_cache_control: false
                    };
                    
                    try {
                        const response = await fetch('/sendmensaje', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify(data)
                        });
                        
                        const result = await response.json();
                        document.getElementById('responseContent').textContent = JSON.stringify(result, null, 2);
                        document.getElementById('response').style.display = 'block';
                    } catch (error) {
                        document.getElementById('responseContent').textContent = 'Error: ' + error.message;
                        document.getElementById('response').style.display = 'block';
                    }
                });
                </script>
            </body>
            </html>
            '''
            self.wfile.write(test_form.encode('utf-8'))
        else:
            self.send_error(404, "Page not found")
    
    def handle_sendmensaje(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            # Parse JSON data
            try:
                data = json.loads(post_data.decode('utf-8'))
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return
            
            # Extract and validate parameters
            api_key = data.get('api_key')
            message = data.get('message')
            assistant_value = data.get('assistant')
            thread_id = data.get('thread_id')
            subscriber_id = data.get('subscriber_id')
            model_id = data.get('ai_provider', '')
            telefono = data.get('telefono')
            direccion_cliente = data.get('direccionCliente')
            
            # Basic validation
            errors = []
            if not message:
                errors.append("Message is required")
            if not subscriber_id:
                errors.append("subscriber_id is required")
            
            if errors:
                self.send_json_response(400, {"error": "; ".join(errors)})
                return
            
            # Generate thread_id if not provided
            if not thread_id:
                import uuid
                thread_id = f"thread_{uuid.uuid4()}"
            
            # Simulate processing (since we can't actually call AI APIs without keys)
            time.sleep(1)  # Simulate processing time
            
            # Create mock response
            mock_response = {
                "thread_id": thread_id,
                "response": f"¡Hola! He recibido tu mensaje: '{message}'. Esta es una respuesta de prueba del asistente {assistant_value}. En un entorno real, me conectaría con {model_id or 'Anthropic'} para procesar tu solicitud sobre el menú de Viking Burger.",
                "usage": {
                    "input_tokens": len(message.split()) * 2,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0
                },
                "status": "test_completed",
                "test_info": {
                    "timestamp": datetime.now().isoformat(),
                    "assistant_type": assistant_value,
                    "model_used": model_id or "anthropic_default",
                    "telefono": telefono,
                    "direccion": direccion_cliente,
                    "note": "Esta es una respuesta simulada para testing"
                }
            }
            
            self.send_json_response(200, mock_response)
            
        except Exception as e:
            self.send_json_response(500, {"error": f"Internal server error: {str(e)}"})
    
    def send_json_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode('utf-8'))
    
    def log_message(self, format, *args):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {format % args}")

def run_test_server(port=8080):
    handler = TestHandler
    
    try:
        with socketserver.TCPServer(("", port), handler) as httpd:
            print(f"🚀 Test server running on http://localhost:{port}")
            print(f"📝 Test interface: http://localhost:{port}/test")
            print(f"🔗 Endpoint: http://localhost:{port}/sendmensaje")
            print("Press Ctrl+C to stop the server")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹️ Server stopped")
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"❌ Port {port} is already in use. Try a different port.")
            return False
        else:
            print(f"❌ Error starting server: {e}")
            return False
    return True

if __name__ == "__main__":
    import sys
    
    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("Invalid port number. Using default port 8080.")
    
    success = run_test_server(port)
    if not success and port == 8080:
        # Try alternative ports
        for alt_port in [8081, 8082, 8083]:
            print(f"Trying port {alt_port}...")
            if run_test_server(alt_port):
                break