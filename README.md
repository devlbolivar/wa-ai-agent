# WhatsApp AI Agent

Sistema de agente conversacional para WhatsApp con IA, construido con FastAPI y LangChain.

## 🚀 Características

- **Autenticación y Autorización**: Sistema de roles (Admin, Agent, User) con JWT.
- **Gestión de Contactos**: CRUD completo de contactos.
- **Conversaciones**: Gestión de hilos conversacionales.
- **Mensajería**: Recepción y envío de mensajes vía WhatsApp.
- **Webhooks**: Manejo de eventos de WhatsApp (mensajes, estados).
- **Middleware**: Body cache y resolución de tenant.
- **Persistencia**: Base de datos PostgreSQL con SQLAlchemy 2.0.
- **Orquestación**: LangChain para flujos de IA.

## 🛠️ Requisitos Previos

- Python 3.12+
- PostgreSQL 13+
- Redis (opcional, para caché)
- Ngrok (para exponer el servidor local a internet)

## 📦 Instalación

1. **Clonar el repositorio**
   ```bash
   git clone <url-del-repositorio>
   cd wa-ai-agent
   ```

2. **Crear un entorno virtual**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows
   # source .venv/bin/activate  # Linux/Mac
   ```

3. **Instalar dependencias**
   ```bash
   pip install -r backend/requirements.txt
   ```

4. **Configuración**
   - Copia el archivo `.env.example` a `.env`:
     ```bash
     cp backend/.env.example backend/.env
     ```
   - Edita `.env` con tus credenciales de base de datos y tokens de WhatsApp.

5. **Base de Datos**
   - Asegúrate de tener PostgreSQL corriendo.
   - Ejecuta las migraciones:
     ```bash
     alembic upgrade head
     ```
   - (Opcional) Seed con datos de prueba:
     ```bash
     python backend/scripts/seed_tenant.py
     ```

## 🏃 Ejecución

1. **Iniciar el servidor**
   ```bash
   uvicorn backend.app.main:app --reload
   ```

2. **Exponer con Ngrok**
   ```bash
   ngrok http 8000
   ```
   Copia la URL de Ngrok (ej: `https://example.ngrok-free.dev`).

3. **Configurar Webhook en Meta**
   - Ve a Meta Developer Portal -> Tu App -> WhatsApp -> Configuración.
   - **URL de retorno de llamada**: Pega la URL de Ngrok + `/api/v1/webhook/whatsapp`.
   - **Token de verificación**: Usa el valor de `WHATSAPP_VERIFY_TOKEN` de tu `.env`.

## 📂 Estructura del Proyecto

```
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── auth.py          # Endpoints de autenticación
│   │       ├── contacts.py      # CRUD de contactos
│   │       ├── conversations.py # Gestión de conversaciones
│   │       ├── health.py        # Health check
│   │       └── webhooks.py      # Webhooks de WhatsApp
│   ├── config.py                # Configuración de la aplicación
│   ├── core/
│   │   ├── auth.py              # Lógica de autenticación
│   │   ├── database.py          # Conexión a BD
│   │   ├── whatsapp_client.py   # Cliente de WhatsApp
│   │   └── security.py          # Seguridad y hashing
│   ├── middleware/
│   │   ├── auth.py              # Middleware de autenticación
│   │   ├── body_cache.py        # Middleware de caché de body
│   │   └── tenant.py            # Middleware de tenant
│   ├── models/
│   │   ├── contact.py           # Modelo Contact
│   │   ├── conversation.py      # Modelo Conversation
│   │   ├── message.py           # Modelo Message
│   │   └── tenant.py            # Modelo Tenant
│   └── main.py                  # Punto de entrada de la app
├── scripts/
│   └── seed_tenant.py           # Script para sembrar datos
├── .env                         # Variables de entorno
├── requirements.txt             # Dependencias
└── pyproject.toml               # Configuración del proyecto
```

## 🧪 Pruebas

### Health Check
```bash
curl http://localhost:8000/api/v1/health
```

### Crear Tenant (Admin)
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "[EMAIL_ADDRESS]", "password": "admin", "role": "admin"}'
```

### Login
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "[EMAIL_ADDRESS]", "password": "admin"}'
```

## 🔐 Roles

- **Admin**: Gestión completa, puede crear agentes.
- **Agent**: Puede ver contactos y conversaciones, responder mensajes.
- **User**: Cliente que interactúa con el agente.

## 📝 Notas de Desarrollo

- El middleware de tenant resuelve el tenant_id a partir del JWT (Week 7).
- Los webhooks se manejan en `app/api/v1/webhooks.py`.
- Se usa SQLAlchemy 2.0 con sessionmaker async.
- LangChain se integrará en futuras versiones para la lógica de IA.

## 🤝 Contribuciones

1. Crear una rama para tu feature:
   ```bash
   git checkout -b feature/nueva-funcionalidad
   ```
2. Hacer cambios y probarlos.
3. Commitear:
   ```bash
   git add .
   git commit -m "feat: descripción de los cambios"
   ```
4. Subir la rama:
   ```bash
   git push origin feature/nueva-funcionalidad
   ```
5. Crear un Pull Request.

## 📄 Licencia

Este proyecto es de código cerrado y propiedad de Luis Bolivar.

## 📞 Soporte

Para problemas o preguntas, contacta al equipo de desarrollo.
