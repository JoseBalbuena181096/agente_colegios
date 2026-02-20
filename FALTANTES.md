# FALTANTES - Agente Colegios San Angel

Lista de pendientes para que el sistema quede listo en produccion.

---

## URGENTE (Bloquean el deploy)

### 1. ~~Location IDs de GHL~~ RESUELTO
- **Archivo**: `app/services/campus_registry.py`, `database/schema.sql`, `database/seed_only.sql`
- **Estado actual**: IDs reales configurados — Puebla=`SOz5nfbI23Xm9mXC51bI`, Poza Rica=`epK2kqk7MkT8t0OBudqP`, Coatzacoalcos=`UNorB3dhUdmtfbdjMAOc`

### 2. ~~Booking link por defecto~~ RESUELTO
- **Archivo**: `app/services/response_service.py` (linea 34), `app/services/advisor_service.py` (linea 133)
- **Estado actual**: Configurado con link de Graciela Castañeda Ulloa: `https://link.superleads.mx/widget/booking/o33ctHxdbcr7Q7wmarJY`

### 3. Asesores de Poza Rica y Coatzacoalcos
- **Archivo**: `database/schema.sql` (lineas 374-380)
- **Estado actual**: Solo Puebla tiene asesores (3). Poza Rica y Coatzacoalcos estan comentados.
- **Accion**: Proporcionar nombre, booking_link y ghl_user_id de los asesores de Poza Rica y Coatzacoalcos

### 4. Variables de entorno (.env)
- **Archivo**: `.env.example`
- **Accion**: Configurar todos los valores reales:
  - `GOOGLE_API_KEY` — API key de Google AI Studio (Gemini)
  - `SUPABASE_URL` — URL del proyecto Supabase de CSA
  - `SUPABASE_TOKEN` — Token/service key de Supabase
  - `token_csa_puebla` — Token GHL sub-cuenta Puebla
  - `token_csa_pozarica` — Token GHL sub-cuenta Poza Rica
  - `token_csa_coatzacoalcos` — Token GHL sub-cuenta Coatzacoalcos
  - `APIFY_API_TOKEN` — Token de Apify (opcional, para scraping de posts)

### 5. Variables faltantes en .env.example
- **Archivo**: `.env.example`
- **Estado actual**: Faltan `OPENAI_API_KEY` y `OPENAI_MODEL` que se usan en `app/services/llm_client.py` (lineas 14, 51)
- **Accion**: Agregar al .env.example (solo si se planea usar OpenAI como alternativa a Gemini)

---

## ALTA PRIORIDAD (Datos incorrectos o inconsistentes)

### 6. Telefonos inconsistentes entre archivos
Los telefonos de Poza Rica y Coatzacoalcos difieren entre `career_agent.py` y `README.md`:

| Plantel | career_agent.py | README.md |
|---------|----------------|-----------|
| Puebla | 222-169-1699 / 222-469-3998 | 222 169 1699 |
| Poza Rica | **782-111-5970** | **782-823-4554** |
| Coatzacoalcos | **921-210-6827** | **921-218-7122** |

- **Archivos**: `app/agents/career_agent.py` (lineas 137-139), `README.md` (lineas 39-41)
- **Accion**: Verificar los telefonos correctos con el equipo de CSA y unificar

### 7. Numero de WhatsApp en comment_agent
- **Archivo**: `app/agents/comment_agent.py` (linea 13)
- **Estado actual**: `https://wa.me/522221691699` (numero de Puebla)
- **Accion**: Verificar si es el WhatsApp correcto para recibir leads de comentarios. Tiene un TODO pendiente en linea 10.

### 8. Direcciones de planteles en el prompt
- **Archivo**: `app/agents/career_agent.py` (lineas 102-139)
- **Estado actual**: Direcciones hardcodeadas en el system prompt del agente
- **Accion**: Verificar que las direcciones sean correctas:
  - Puebla: Av. Orion Sur 1549, Col. Reserva Territorial Atlixcayotl, C.P. 72590
  - Poza Rica: Carr. Poza Rica - Cazones Fraccion A2, Parcela 26B, Col. La Rueda, C.P. 93306
  - Coatzacoalcos: Col. Predio Rustico Santa Rosa, Av. Universidad Veracruzana 2920, Fovissste, C.P. 96536
- **Nota**: Idealmente mover a tabla `campuses` en Supabase y consultar via `campus_service`

---

## MEDIA PRIORIDAD (Necesario para produccion completa)

### 9. Migraciones de base de datos
- **Archivo**: `database/schema.sql`
- **Accion**: Ejecutar en Supabase SQL Editor. Luego poblar:
  - Tabla `campuses`: 3 planteles con location_ids y website_url
  - Tabla `careers`: Niveles educativos por plantel (Preescolar, Primaria, Secundaria, Bachillerato) con URLs
  - Tabla `advisors`: Asesores por plantel con booking links (round robin)
  - Tabla `objection_playbook`: Objeciones adaptadas al contexto K-12 de CSA (precios, becas, horarios, transporte, etc.)

### 10. Configuracion de webhooks
- **GHL**: Configurar webhooks apuntando a:
  - `POST /webhook_conversations` — Mensajes entrantes (FB, IG, WA, SMS)
  - `POST /webhook_facebook` — Comentarios en posts de Facebook
  - `POST /webhook_instagram` — Comentarios en posts de Instagram
- **Meta Developer**: Configurar webhooks de Facebook/Instagram para recibir comentarios en posts

### 11. Objection playbook adaptado a K-12
- **Tabla**: `objection_playbook` en Supabase
- **Estado actual**: El codigo espera categorias de objeciones pero la tabla esta vacia
- **Accion**: Crear objeciones relevantes para Colegios (no universitarias):
  - Colegiaturas y costos
  - Becas y descuentos
  - Horarios y actividades extraescolares
  - Transporte escolar
  - Metodologia educativa
  - Instalaciones y seguridad
  - Proceso de inscripcion
  - Uniformes y materiales

---

## BAJA PRIORIDAD (Mejoras y limpieza)

### 12. Tests unitarios
- **Directorio**: `tests/` (vacio)
- **Accion**: Crear tests adaptados para CSA, al menos:
  - `test_campus_registry.py` — Verificar los 3 planteles
  - `test_data_extraction.py` — Regex de telefono, email, nivel educativo
  - `test_safety_nets.py` — Keywords admin, greeting loops
  - `test_career_agent.py` — Prompts y kill switch

### 13. Comentarios DEBUG en codigo
- **Archivos afectados**:
  - `app/agents/career_agent.py` linea 290: `logger.info("DEBUG KILL SWITCH: ...")`
  - `app/services/apify_service.py` lineas 133-134, 232-233: `"DEBUG - Campos del resultado"`
- **Accion**: Cambiar `logger.info("DEBUG ...")` a `logger.debug(...)` o eliminar antes de produccion

### 14. Mover info de planteles a base de datos
- **Estado actual**: Direcciones, telefonos y horarios de planteles estan hardcodeados en el system prompt de `career_agent.py`
- **Accion futura**: Moverlos a la tabla `campuses` y consultarlos via `get_campus_info` tool, para poder actualizarlos sin deploy

### 15. Configurar deploy en Railway
- **Archivos**: `railway.json`, `Procfile`
- **Accion**: Verificar que la configuracion de Railway apunte al proyecto correcto y que las variables de entorno esten configuradas en el dashboard

---

## CHECKLIST RAPIDO

```
[x] Location IDs reales en campus_registry.py
[x] Booking links reales en response_service.py y advisor_service.py
[ ] Variables .env configuradas
[ ] Telefonos verificados y unificados
[ ] WhatsApp verificado en comment_agent.py
[ ] Direcciones verificadas en career_agent.py
[x] Booking links reales en response_service.py y advisor_service.py (Graciela Castañeda como default)
[x] Schema SQL completo con 7 tablas + seed data (database/schema.sql)
[x] Tabla campuses poblada (3 planteles con location IDs reales)
[x] Tabla careers poblada (11 niveles: 4 Puebla + 3 Poza Rica + 4 Coatzacoalcos)
[x] Tabla advisors Puebla (3 asesores con booking links reales)
[ ] Tabla advisors Poza Rica y Coatzacoalcos — pendiente datos de asesores
[x] Tabla objection_playbook poblada (9 objeciones K-12)
[ ] Webhooks GHL configurados
[ ] Webhooks Meta configurados
[ ] Deploy en Railway configurado
[ ] Tests basicos creados
```
