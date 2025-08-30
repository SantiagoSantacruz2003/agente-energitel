# Configuración de Redis para Manejo de Hilos

## Configuración Actual

El sistema ahora soporta Redis para almacenar hilos de conversación con las siguientes características:

### ✅ Implementado:
- **TTL automático**: Los hilos se eliminan automáticamente después de 2 horas
- **Limpieza programada**: Un hilo ejecuta limpieza cada hora como backup
- **Conexión simplificada**: Usa `REDIS_URL` para mayor simplicidad
- **Fallback a memoria**: Si Redis falla, usa almacenamiento local

### Configuración Simple con REDIS_URL

En tu archivo `.env`, solo necesitas configurar:

```bash
# Activar Redis
USE_REDIS=true

# URL de conexión de tu proveedor Redis
REDIS_URL=redis://username:password@host:port/database

# Ejemplo con proveedor externo:
# REDIS_URL=redis://default:tu_password@redis.tu-proveedor.com:6379
```

### Configuración Manual (Alternativa)

Si prefieres usar variables individuales en lugar de REDIS_URL:

```bash
USE_REDIS=true
REDIS_HOST=tu-host-redis.com
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=tu_password
REDIS_CONNECTION_POOL_SIZE=10
```

## Instalación de Redis Python Client

Asegúrate de tener el cliente Redis instalado:

```bash
pip install redis
```

O si usas el archivo requirements.txt, ya debería estar incluido.

## Funcionalidades

### 1. **Almacenamiento Persistente**
- Los hilos se almacenan en Redis en lugar de memoria local
- Sobreviven a reinicios del servidor
- Compartidos entre múltiples instancias si es necesario

### 2. **Expiración Automática (2 horas)**
- **TTL nativo de Redis**: Cada hilo se auto-elimina después de 2 horas
- **Limpieza programada**: Backup que ejecuta cada hora
- **Renovación automática**: El TTL se renueva con cada actividad

### 3. **Logs de Debug**
El sistema incluye logs detallados para debugging:
- Configuración de Redis al iniciar
- Estado de conexión
- Operaciones de almacenamiento/recuperación
- Limpieza de hilos expirados

## Verificación

Para verificar que Redis está funcionando, revisa los logs al iniciar la aplicación:

```
INFO - Configuración Redis - USE_REDIS: True
INFO - REDIS_URL: redis://default:***... (usando URL directa)
INFO - Inicializando ConversationManager - Redis: True
INFO - Intentando conectar a Redis con configuración: {'url': 'redis://...', 'ttl_seconds': 7200}
INFO - Conectando usando REDIS_URL: redis://default:***...
INFO - Probando conexión Redis...
INFO - Redis ping exitoso: True
INFO - RedisConversationManager inicializado exitosamente - TTL: 7200s
INFO - ConversationManager inicializado exitosamente - Tipo: RedisConversationManager
INFO - Hilo de limpieza iniciado - TTL: 2 horas
```

## Proveedores Redis Recomendados

Para uso en producción, considera estos proveedores:
- **Railway**: Redis como servicio
- **Redis Cloud**: Servicio oficial de Redis
- **AWS ElastiCache**: Redis gestionado
- **DigitalOcean**: Redis Managed Database
- **Upstash**: Redis serverless

Todos proporcionan una URL de conexión que puedes usar directamente en `REDIS_URL`.