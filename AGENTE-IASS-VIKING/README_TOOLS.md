# Guía de Function Tools con N8N Bridge

## Añadir nuevas Function Tools (con n8n)

### 1. Declarar la tool en el archivo JSON del asistente

Las herramientas deben declararse en el archivo correspondiente al asistente (`tools/tools_<n>.json`), usando el formato correcto de OpenAI Tools:

```json
[
  {
    "type": "function",
    "name": "cambiar_nombre",
    "description": "Cambia el nombre del cliente en el sistema",
    "parameters": {
      "type": "object",
      "properties": {
        "nombre": {
          "type": "string", 
          "description": "Nombre completo del cliente (nombre y apellido)"
        }
      },
      "required": ["nombre"]
    }
  }
]
```

**IMPORTANTE**: 
- `name` debe estar en el **nivel superior**, no anidado dentro de `function.name`
- El asistente solo verá tools del archivo que le corresponde según `ASSISTANT_TOOLS` en `app/endpoints.py`

### 2. Mapear la tool a un webhook n8n

En `app/n8n_bridge.py`, agregar la configuración del webhook:

```python
N8N_WEBHOOKS["cambiar_nombre"] = {
    "url": os.getenv("N8N_CAMBIAR_NOMBRE_URL", "https://TU-N8N/webhook/cambiar_nombre"),
    "method": "POST",
    "headers": {"Content-Type": "application/json"},
    "timeout": 25
}
```

### 3. Configurar variable de entorno (opcional)

Si usas variables de entorno para las URLs:

```bash
export N8N_CAMBIAR_NOMBRE_URL="https://tu-n8n.dominio.com/webhook/cambiar_nombre"
```

### 4. ¡Listo!

No hay que tocar Python en ningún otro lado. El flujo funciona así:

1. El LLM llama la tool
2. El handler la detecta como "function" 
3. Se envía automáticamente a n8n mediante el bridge

## Payload enviado a N8N

El **payload estándar** que recibe cada webhook de n8n es:

```json
{
  "ai_data": {
    // ...argumentos específicos de la tool...
  },
  "subscriber_id": "user_123",
  "thread_id": "thread_456", 
  "assistant": 0,
  "tool_name": "cambiar_nombre",
  "timestamp": "2025-01-15T10:30:45.123456Z"
}
```

**Nota**: Las herramientas **MCP mantienen su flujo original** y no usan este bridge.

## Mapeo Asistente ↔ Tools

Los asistentes están limitados a sus herramientas específicas:

```python
ASSISTANT_TOOLS = {
    0: "tools/tools_0.json",
    1: "tools/tools_1.json", 
    2: "tools/tools_2.json",
    # ...
    5: "tools/default_tools.json"  # Default/fallback
}
```

## Buenas prácticas

- **Validaciones de negocio** → En n8n o en el JSON Schema de la tool
- **Manejo de errores** → El bridge maneja timeouts y HTTP 4xx/5xx automáticamente
- **Separación de responsabilidades** → No mezclar config de n8n dentro de los JSON de tools
- **URLs dinámicas** → Usar variables de entorno para diferentes ambientes

## Ejemplo completo: Crear nueva tool "crear_pedido"

### 1. En `tools/tools_0.json`:

```json
[
  {
    "type": "function",
    "name": "crear_pedido",
    "description": "Crea un nuevo pedido en el sistema",
    "parameters": {
      "type": "object",
      "properties": {
        "cliente_id": {
          "type": "string",
          "description": "ID único del cliente"
        },
        "producto": {
          "type": "string", 
          "description": "Nombre del producto a pedir"
        },
        "cantidad": {
          "type": "integer",
          "description": "Cantidad de productos",
          "minimum": 1
        }
      },
      "required": ["cliente_id", "producto", "cantidad"]
    }
  }
]
```

### 2. En `app/n8n_bridge.py`:

```python
N8N_WEBHOOKS["crear_pedido"] = {
    "url": os.getenv("N8N_CREAR_PEDIDO_URL", "https://tu-n8n.com/webhook/crear_pedido"),
    "method": "POST", 
    "headers": {"Content-Type": "application/json"},
    "timeout": 30
}
```

### 3. El webhook en n8n recibirá:

```json
{
  "ai_data": {
    "cliente_id": "cliente_123",
    "producto": "Laptop Dell",
    "cantidad": 2
  },
  "subscriber_id": "user_456",
  "thread_id": "thread_789",
  "assistant": 0,
  "tool_name": "crear_pedido", 
  "timestamp": "2025-01-15T10:30:45.123456Z"
}
```

## Troubleshooting

### Error: Tool no configurada
```
{"error": "Tool 'mi_tool' no configurada en N8N_WEBHOOKS"}
```
**Solución**: Agregar la tool a `N8N_WEBHOOKS` en `app/n8n_bridge.py`

### Error: Tool no encontrada por el asistente
**Solución**: Verificar que la tool esté en el archivo JSON correcto según `ASSISTANT_TOOLS`

### Error: Timeout o HTTP 4xx/5xx
**Solución**: Verificar que la URL del webhook n8n sea correcta y esté funcionando