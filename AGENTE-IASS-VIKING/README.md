# AGENTE IASS ENERGITEL ⚡🤖

## Descripción General

Esta aplicación es un **sistema de asistente conversacional inteligente** diseñado específicamente para manejar servicios de energía eléctrica (Energitel). Utiliza múltiples modelos de LLM (Large Language Models) como Anthropic Claude, OpenAI GPT, y Google Gemini para procesar conversaciones de clientes y ejecutar acciones específicas del negocio mediante MCP (Model Context Protocol).

## Arquitectura del Sistema

### 🏗️ Estructura Modular

La aplicación está organizada en una arquitectura modular para facilitar el mantenimiento y debugging:

```
AGENTE-IASS-ENERGITEL/
├── app/
│   ├── app.py                   # Aplicación Flask principal
│   ├── endpoints.py             # Definición de todos los endpoints HTTP
│   ├── llm_handlers.py          # Manejadores de modelos LLM
│   ├── conversation_manager.py  # 🆕 Sistema de gestión de conversaciones (Redis/Memory)
│   ├── cleanup.py               # Sistema de limpieza de conversaciones (2h TTL)
│   ├── services/
│   │   └── n8n_service.py       # Integración con n8n para automatización
│   └── utils.py                 # Funciones utilitarias
├── tools/                       # Configuraciones de herramientas por etapa
├── PROMPTS/ENERGITEL/           # Plantillas de prompts para asistentes
├── config/                      # Configuraciones de servicios
├── .env                         # Variables de entorno
├── .env.example                 # 🆕 Template de configuración con Redis
├── test_redis_migration.py      # 🆕 Suite de pruebas Redis/Memory
└── REDIS_MIGRATION.md           # 🆕 Documentación migración Redis
```

### 🔄 Flujo de Funcionamiento

1. **Recepción de Mensaje**: Cliente envía mensaje via `/sendmensaje`
2. **Selección de LLM**: Basado en `modelID` se elige el modelo apropiado
3. **Carga de Contexto**: Se carga el prompt del asistente según la etapa
4. **Procesamiento**: El LLM procesa el mensaje y puede ejecutar herramientas
5. **Ejecución de Acciones**: Se ejecutan funciones específicas del negocio
6. **Respuesta**: Se devuelve la respuesta procesada al cliente

## 🧠 Modelos LLM Soportados

### 1. Anthropic Claude (Por defecto)
- **Modelo**: `claude-3-5-haiku-latest`
- **Activación**: Sin especificar `modelID` o `modelID != 'llmo'|'llmg'`
- **Características**: 
  - Cache control para optimización
  - Manejo robusto de herramientas
  - Reintentos automáticos con backoff exponencial

### 2. OpenAI GPT
- **Modelo**: `gpt-4.1` / `gpt-4.1-mini`
- **Activación**: `modelID: 'llmo'`
- **Características**:
  - Responses API nueva
  - Function calling
  - Manejo de tokens detallado

### 3. Google Gemini
- **Modelo**: `gemini-2.5-pro-exp-03-25`
- **Activación**: `modelID: 'llmg'`
- **Características**:
  - Google GenAI SDK
  - Function declarations
  - Temperatura ajustable (0.9)

## 🎯 Sistema de Asistentes por Etapas

La aplicación maneja diferentes tipos de asistentes según la etapa del proceso:

### Etapas Definidas:
- **Etapa 0**: `ASISTENTE_INICIAL` - Bienvenida y captura inicial
- **Etapa 1**: `ASISTENTE_DOMICILIO` - Manejo de entregas a domicilio  
- **Etapa 2**: `ASISTENTE_RECOGER` - Pedidos para recoger
- **Etapa 3**: `ASISTENTE_FORMA_PAGO` - Procesamiento de pagos
- **Etapa 4**: `ASISTENTE_POSTVENTA` - Servicio post-venta
- **Etapa 5**: `ASISTENTE_INICIAL_FUERA_DE_HORARIO` - Atención fuera de horario

### Carga de Herramientas por Etapa:
```javascript
// Mapeo de etapas a archivos de herramientas
Etapa 0 → tools_stage0.json / tools_stage0_gemini.json
Etapa 1,2 → tools_stage1.json / tools_stage1_gemini.json  
Etapa 3 → tools_stage2.json / tools_stage2_gemini.json
Etapa 4,5 → tools_stage3.json / tools_stage3_gemini.json
```

## 🛠️ Herramientas y Acciones Disponibles

### Herramientas Principales:
1. **`crear_pedido`** - Crea pedidos en el sistema
2. **`crear_link_pago`** - Genera enlaces de pago
3. **`enviar_menu`** - Envía el menú al cliente
4. **`crear_direccion`** - Registra direcciones de entrega
5. **`eleccion_forma_pago`** - Procesa selección de método de pago
6. **`facturacion_electronica`** - Maneja facturación electrónica
7. **`pqrs`** - Gestiona peticiones, quejas y reclamos

### Integración con n8n:
- Todas las herramientas están conectadas con flujos de n8n
- Automatización de procesos empresariales
- Webhooks para notificaciones y actualizaciones

## 📡 API Endpoints

### 🔥 Endpoint Principal: `/sendmensaje` (POST)

Endpoint principal para procesamiento de conversaciones.

**Parámetros de Entrada:**
```json
{
  "api_key": "string",           // API key del LLM (opcional para algunos)
  "message": "string",           // Mensaje del cliente (requerido)
  "assistant": "integer",        // Número de etapa del asistente (0-5)
  "thread_id": "string",         // ID único de conversación
  "subscriber_id": "string",     // ID del cliente (requerido)
  "thinking": "integer",         // Activar modo thinking (0|1)
  "modelID": "string",           // Selector de LLM ('llmo'|'llmg'|default)
  "telefono": "string",          // Teléfono del cliente
  "direccionCliente": "string",  // Dirección del cliente
  "use_cache_control": "boolean", // Control de caché (Anthropic)
  "llmID": "string",             // ID específico del modelo
  // Variables adicionales para sustitución en prompts
  "nombreCliente": "string",
  "ciudadCliente": "string",
  // ... más variables según necesidad
}
```

**Respuesta:**
```json
{
  "thread_id": "string",
  "response": "string",
  "usage": {
    "input_tokens": "integer",
    "output_tokens": "integer", 
    "cache_creation_input_tokens": "integer",
    "cache_read_input_tokens": "integer"
  },
  "razonamiento": "string"
}
```

### 🔧 Endpoints Utilitarios:

#### `/extract` (POST)
Extrae información estructurada de datos de entrada.
```json
// Entrada
{
  "nombre": "string",
  "apellido": "string", 
  "cedula": "string",
  "ciudad": "string",
  "solicitud": "string",
  "contactar": "string"
}
```

#### `/letranombre` (POST) 
Genera avatares SVG basados en iniciales.
```json
// Entrada
{"text": "Juan Perez"}
// Salida: Múltiples resoluciones de avatar SVG
```

#### `/time` (POST)
Convierte formatos de tiempo.
```json
// Entrada
{"datetime": "2024-01-01T10:00:00"}
// Salida  
{"original": "...", "converted": "..."}
```

#### `/upload` (POST)
Sube archivos a Freshsales CRM.

#### `/linkpago` (GET)
Procesa enlaces de pago y redirecciona a Bold.
```
GET /linkpago?id=123&telefono=555&link=abc123&forma=tarjeta
```

#### `/crearactividad` (POST)
Crea actividades en Odoo CRM.

#### `/crearevento` (POST)  
Crea eventos de calendario en Odoo.

#### `/leeractividades` (POST)
Lee actividades asociadas a oportunidades en Odoo.

## 🔧 Configuración y Variables de Entorno

### Variables de Entorno Requeridas (.env):
```bash
# APIs de LLM
ANTHROPIC_API_KEY=your_anthropic_key
OPENAI_API_KEY=your_openai_key  
GEMINI_API_KEY=your_gemini_key
DEEPSEEK_API_KEY=your_deepseek_key

# Webhooks n8n - Principales
N8N_CREAR_PEDIDO_WEBHOOK_URL=https://n8niass.cocinandosonrisas.co/webhook/crearPedidoTheVikingBurgerApi
N8N_LINK_PAGO_WEBHOOK_URL=https://n8niass.cocinandosonrisas.co/webhook/linkPagoTheVikingBurgerApi
N8N_ENVIAR_MENU_WEBHOOK_URL=https://n8niass.cocinandosonrisas.co/webhook/enviarMenuTheVikingBurgerApi
N8N_CREAR_DIRECCION_WEBHOOK_URL=https://n8niass.cocinandosonrisas.co/webhook/crearDireccionTheVikingBurgerApi
N8N_ELECCION_FORMA_PAGO_WEBHOOK_URL=https://n8niass.cocinandosonrisas.co/webhook/eleccionFormaPagoTheVikingBurgerApi
N8N_FACTURACION_ELECTRONICA_WEBHOOK_URL=https://n8niass.cocinandosonrisas.co/webhook/facturacionElectronicaTheVikingBurgerApi
N8N_PQRS_WEBHOOK_URL=https://n8niass.cocinandosonrisas.co/webhook/pqrsTheVikingBurgerApi

# Webhooks n8n - Adicionales (anteriormente hardcodeados)
N8N_IMPRESION_COMANDA_WEBHOOK_URL=https://n8niass.cocinandosonrisas.co/webhook/impresionComandaTheVikingBurgerApi
N8N_PEDIDO_LISTO_WEBHOOK_URL=https://n8niass.cocinandosonrisas.co/webhook/pedidoListoTheVikingBurgerApi
N8N_CREACION_LINK_PAGO_WEBHOOK_URL=https://n8niass.cocinandosonrisas.co/webhook/creacionLinkPagoTheVikingBurgerApi
N8N_INFO_WOMPI_WEBHOOK_URL=https://n8niass.cocinandosonrisas.co/webhook/infoWompi2030HamburgueseriaApi

# Webhooks n8n - Legacy/Compatibilidad
N8N_WEBHOOK_URL=https://n8niass.cocinandosonrisas.co/webhook/eleccionFormaPagoTheVikingBurgerApi
WEBHOOK_URL_NUEVO_LINK=https://...

# Freshsales CRM
FRESHSALES_API_KEY=your_freshsales_key
FRESHSALES_BASE_URL=https://your_domain.myfreshworks.com

# Configuración adicional
DEBUG=true
FLASK_ENV=development
```

## 💾 Sistema de Gestión de Conversaciones

### Estructura de Conversación:
```python
conversations[thread_id] = {
    "status": "processing|completed|error",
    "response": "string",
    "messages": [],              # Historial de mensajes
    "assistant": "integer",      # Etapa actual
    "thinking": "integer",       # Modo thinking
    "telefono": "string",
    "direccionCliente": "string", 
    "usage": {},                 # Información de tokens
    "last_activity": "timestamp" # Para limpieza automática
}
```

### Limpieza Automática:
- **Tiempo de expiración**: 2 horas de inactividad
- **Frecuencia de limpieza**: Cada hora
- **Implementación**: Hilo en segundo plano (`cleanup.py`)

### Concurrencia:
- **Threading**: Cada conversación tiene su propio lock
- **Timeout**: 60 segundos por respuesta
- **Seguridad**: Locks por thread_id para evitar condiciones de carrera

## 🔌 Integraciones Externas

### 1. n8n (Automatización)
- **Propósito**: Flujos de trabajo automatizados
- **Conexión**: Webhooks HTTP
- **Funciones**: Todas las herramientas del LLM ejecutan acciones en n8n

### 2. Freshsales CRM
- **Propósito**: Gestión de clientes y documentos
- **Endpoint**: `/upload`
- **Autenticación**: Token API

### 3. Odoo CRM
- **Propósito**: Gestión empresarial completa
- **Endpoints**: `/crearactividad`, `/crearevento`, `/leeractividades`
- **Conexión**: XML-RPC

### 4. Bold (Pagos)
- **Propósito**: Procesamiento de pagos
- **Endpoint**: `/linkpago`
- **Flujo**: Redirect a checkout de Bold

## 🚀 Instalación y Despliegue

### Dependencias Principales:
```
Flask==2.3.3
anthropic==0.25.0
openai==1.12.0
google-genai==0.7.0
requests==2.31.0
python-dotenv==1.0.0
beautifulsoup4==4.12.2
pytz==2023.3
```

### Comandos de Instalación:
```bash
# Clonar repositorio
git clone [repository_url]
cd AGENTE-IASS-VIKING

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# Ejecutar aplicación
python app/app.py
```

### Estructura de Despliegue:
- **Puerto**: 8080
- **Host**: 0.0.0.0 (todas las interfaces)
- **Entorno**: Producción/Desarrollo según FLASK_ENV

## 🐛 Debugging y Logging

### Sistema de Logging:
- **Nivel**: INFO por defecto
- **Formato**: `%(asctime)s [%(levelname)s] %(message)s`
- **Salida**: Consola (StreamHandler)

### Logs Importantes:
- Inicio/fin de conversaciones
- Llamadas a APIs de LLM
- Ejecución de herramientas
- Errores y excepciones
- Información de tokens/costos

### Debugging por Módulo:
- **`llm_handlers.py`**: Problemas con LLMs y herramientas
- **`endpoints.py`**: Problemas con endpoints HTTP
- **`cleanup.py`**: Problemas de memoria y limpieza
- **`n8n_service.py`**: Problemas de integración

## 🔒 Seguridad y Mejores Prácticas

### Manejo de API Keys:
- ✅ Almacenadas en variables de entorno
- ❌ Nunca hardcodeadas en código
- ⚠️ **IMPORTANTE**: Hay una clave hardcodeada en `tools_test.py` línea 46 que debe eliminarse

### Validaciones:
- Validación de parámetros obligatorios
- Verificación de estructura de mensajes
- Timeouts en requests externos
- Manejo de excepciones robusto

### Reintentos y Resilencia:
- Reintentos automáticos con backoff exponencial
- Timeouts configurables
- Manejo graceful de errores de API

## 📊 Monitoreo y Métricas

### Métricas de Tokens:
- Input tokens consumidos
- Output tokens generados  
- Cache hits/misses
- Costos por conversación

### Métricas de Rendimiento:
- Tiempo de respuesta por LLM
- Throughput de conversaciones
- Errores por endpoint
- Uso de memoria

## 🔄 Flujo de Datos Típico

### Ejemplo: Pedido de Hamburguesa
```
1. Cliente: "Quiero una hamburguesa"
   ↓
2. /sendmensaje → modelID='llmg' → Gemini
   ↓  
3. Gemini carga tools_stage0_gemini.json
   ↓
4. Gemini ejecuta enviar_menu()
   ↓
5. n8n recibe webhook → envía menú por WhatsApp
   ↓
6. Cliente selecciona → assistant=1 (domicilio)
   ↓
7. Gemini ejecuta crear_direccion()
   ↓
8. Flujo continúa hasta crear_link_pago()
   ↓
9. Cliente redirección a Bold para pago
```

## 🚨 Problemas Conocidos y Limitaciones

### Limitaciones Actuales:
1. **Memoria**: Conversaciones se almacenan en memoria (no persistente)
2. **Escalabilidad**: Single-threaded para cada conversación
3. **API Keys**: Gemini requiere configuración manual
4. **Dependencias**: Requiere n8n funcionando para herramientas

### Mejoras Recomendadas:
1. **Redis**: Implementar almacenamiento persistente
2. **Rate Limiting**: Control de velocidad de requests
3. **Health Checks**: Endpoints de salud
4. **Metrics**: Integración con Prometheus/Grafana
5. **Docker**: Containerización para despliegue

## 📋 Casos de Uso Principales

### 1. Restaurante/Comida Rápida
- Toma de pedidos automatizada
- Gestión de entregas y recolecciones  
- Procesamiento de pagos
- Atención al cliente 24/7

### 2. CRM/Ventas
- Calificación de leads
- Seguimiento de oportunidades
- Creación de actividades y eventos
- Gestión documental

### 3. Soporte Técnico
- PQRS automatizadas
- Escalamiento inteligente
- Base de conocimiento
- Métricas de satisfacción

## 🤝 Contribución y Desarrollo

### Estructura para Nuevas Funcionalidades:
1. **Herramientas**: Agregar en `n8n_service.py`
2. **Endpoints**: Agregar en `endpoints.py`  
3. **LLM Logic**: Modificar `llm_handlers.py`
4. **Prompts**: Crear en `prompts/URBAN/`
5. **Tools Config**: Actualizar JSONs en `tools/`

### Testing:
- `tools_test.py`: Tests de herramientas
- `test_app.py`: Tests de endpoints
- `test_endpoint.py`: Tests específicos

---

Este README proporciona un contexto completo para que cualquier IA pueda entender la arquitectura, funcionalidad y propósito de la aplicación AGENTE IASS VIKING BURGER.