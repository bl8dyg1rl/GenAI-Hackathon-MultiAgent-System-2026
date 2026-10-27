# Colombia Data Intelligence — MVP multiagente en Python

Chat web sencillo para descubrir estadísticas públicas de Colombia. La coordinación está en Python; FastAPI solo conecta el navegador con el orquestador. Todos los modelos se llaman exclusivamente mediante el proveedor OpenAI-compatible de **Meterless Nightshift**. **Zetaris es la única capa que consulta filas de datos**: la búsqueda pública externa se limita a metadatos del catálogo de Datos Abiertos Colombia.

## Arquitectura implementada

- **Scout Intent (Python):** clasifica intención, aplica una guardia de entrada, arma rutas/capacidades y firma contratos de ejecución HMAC con expiración. Las herramientas verifican el contrato antes de actuar. El diseño sigue el [Scout Intent Agnostic Implementation Guide](https://github.com/Meterless/Meterless/blob/main/engines/scout-intent/AGENTS.md), pero es una implementación propia de esta aplicación; no es el paquete oficial ni se afirma que haya pasado su eval harness.
- **Data Scout:** llama a Nightshift para elegir términos de búsqueda, descubre metadatos del catálogo oficial y comparte candidatos con el Analyst.
- **Query & Stats Analyst:** consulta en paralelo las tablas permitidas de Zetaris para inspeccionar sus esquemas. Recibe candidatos por el tablero compartido, usa Nightshift para formular una consulta y solo ejecuta `SELECT` con `LIMIT` contra tablas allowlisted.
- **Evidence Auditor:** inspecciona procedencia, filas, tabla y límites. Puede enviar una solicitud concreta al Analyst y provocar una única corrección de consulta.
- **Answer Composer:** usa Nightshift para redactar en español y recibe solo evidencia estructurada, el resultado de Zetaris, la auditoría y las limitaciones.
- **Tablero compartido y registro:** SQLite guarda eventos, solicitudes/respuestas de modelo, mensajes entre agentes, herramientas llamadas, contratos y resultado de cada ejecución. El evento de log no incluye cabeceras de autenticación; los campos de credenciales se redactan.

La búsqueda de metadatos y la inspección del esquema ocurren en paralelo. Los agentes intercambian resultados por mensajes persistidos. Por eso no es una cadena lineal fija: Data Scout entrega candidatos al Analyst y el Auditor puede pedirle al Analyst que corrija una consulta.

## Requisitos

1. Python 3.11 o superior.
2. Meterless Nightshift instalado y en ejecución, con un Runtime token real.
3. Zetaris en ejecución, con al menos una fuente/tabla estadística colombiana registrada y permisos de lectura por REST API.

La app no registra automáticamente los datasets por ti en Zetaris. La integración consulta las tablas que configures explícitamente.

## Instalar y ejecutar en Windows

Extrae el ZIP completo en una carpeta como `D:\Users\USUARIO\Desktop\Zetaris\colombia-data-intelligence`.

Abre PowerShell en esa carpeta y ejecuta:

```powershell
.\setup.ps1
.\run.ps1
```

Abre `http://127.0.0.1:8000`. FastAPI sirve el chat localmente; no se expone a otros equipos porque Uvicorn se inicia con `127.0.0.1`.

El instalador crea un secreto local aleatorio para firmar contratos de Scout Intent. No compartas el archivo `.env`.

Para ejecutar las pruebas automatizadas:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Configurar Meterless Nightshift

En el chat abre **Ajustes** y configura:

- **Runtime base URL:** por defecto `http://127.0.0.1:8088/v1`, si coincide con el hotspot de tu instalación.
- **Runtime token:** el token real que entrega Nightshift. El placeholder `rt-local` es rechazado por el contrato del proveedor.
- **Modo de enrutamiento:** usa `Descubrir modos` y selecciona uno de los `meterless/*` que devuelve tu Runtime. Si el Runtime devuelve un ID no conocido por la interfaz, también se conserva en la lista.

Haz estas comprobaciones en orden: **Probar conexión / auth / modelos**, **Descubrir modos**, **Probar texto**. El proveedor envía `Authorization: Bearer ...`, `meterless-app: colombia-data-intelligence` y `meterless-scope: user` en el chat. Las solicitudes de texto tienen timeout de hasta tres minutos porque el Runtime puede estar cargando el modelo.

Todas las llamadas de modelo de los agentes pasan por `ModelGateway → MeterlessClient → Nightshift`; no hay fallback silencioso a OpenAI, Gemini u otro proveedor.

## Configurar Zetaris

### 1. Registrar fuentes / tablas

En Zetaris conecta una fuente estadística oficial (por ejemplo, un dataset del catálogo colombiano que hayas registrado como fuente REST) y verifica que la tabla se pueda consultar en tu instancia. Una fuente que solo se haya descubierto en el catálogo público no queda automáticamente registrada en Zetaris.

### 2. Configurar la API de consulta

En **Ajustes → Zetaris** usa por defecto:

- **REST API base URL:** `http://127.0.0.1:8888/api/v1.0` para el entorno local actual, si tu instancia expone allí la API REST.
- **Ruta de consulta SQL:** `sql-editor/sqls/run-query`.
- **Token / idToken:** el token de autenticación de la API Zetaris con permiso de lectura.
- **Tablas permitidas:** nombres exactos de las tablas que registraste, por ejemplo `COLOMBIA_STATS.desempleo, COLOMBIA_STATS.pib`. Son solo ejemplos, no tablas que este ZIP haya creado en tu instancia.
- **Mapeo opcional:** un objeto JSON que conecte el ID de un dataset del catálogo a la tabla registrada. Ejemplo sintáctico: `{"abcd-1234":"COLOMBIA_STATS.desempleo"}`. Cambia el ID y el nombre de tabla por valores reales.

Pulsa **Guardar Zetaris** y **Probar tabla / consulta**. El adaptador sigue el contrato REST documentado por Zetaris: `POST <base>/sql-editor/sqls/run-query` con cuerpo `{ "select": "SELECT ...", "pageLimit": 100 }`. Envía `Authorization: Bearer <idToken>` y un `requestId`. El endpoint o la forma de autenticación pueden variar según la distribución/entorno de Zetaris; si hay un 401/403, confirma el token y los permisos. Consulta también [Accessing Zetaris through REST API](https://kbase.zetaris.com/knowledge/rest-api).

También puedes establecer estos valores en `.env` antes de iniciar la aplicación. Los tokens que escribas en Ajustes viven solo en la memoria del backend; al reiniciarlo, vuelve a introducirlos o configura las variables de entorno. **Nunca subas `.env` ni `data/agent_runs.sqlite3` al repositorio.**

## Registro de actividad

El archivo `data/agent_runs.sqlite3` registra las ejecuciones, interacciones entre agentes, mensajes enviados/recibidos, prompts/respuestas de modelo y resúmenes de herramientas. La pestaña **Actividad** bajo cada respuesta muestra la ruta que tomó la ejecución; los endpoints locales también están disponibles:

- `GET /api/runs/recent`
- `GET /api/runs/{run_id}/events`
- `GET /api/runs/{run_id}/messages`

Los prompts y las respuestas de agentes se guardan localmente para poder auditar una ejecución; por eso no compartas la base SQLite si contiene preguntas privadas. El token de Runtime y el token de Zetaris no se guardan dentro de estos eventos.

## Seguridad y límites

- Solo se aceptan consultas `SELECT` que nombren tablas de la lista permitida. El adaptador añade `LIMIT 100` si falta y rechaza límites mayores a 100, múltiples sentencias, comentarios SQL y operaciones DDL/DML.
- El catálogo externo se utiliza para descubrir **metadatos**. No se descargan filas de Socrata directamente desde la app; las filas usadas en el análisis salen de Zetaris.
- Si no hay una tabla registrada/permitida, el chat puede mostrar metadatos candidatos, pero debe informar que no obtuvo evidencia estadística de Zetaris.
- El auditor impide que una consulta vacía se trate como evidencia estadística suficiente. Una respuesta del modelo no reemplaza las filas ni los metadatos.
- Scout Intent es la implementación Python de la aplicación basada en la guía pública agnóstica. Para afirmar conformidad con Meterless, aún habría que ejecutar y superar el harness oficial de Scout Intent.
- H-MEM, Markovian y World Model **no están integrados como motores oficiales** en esta versión. SQLite aquí es el tablero/registro local compartido, no una implementación certificada de World Model.
- Las pruebas incluidas usan respuestas simuladas para no necesitar credenciales en CI. Son pruebas unitarias, no certifican que tu Runtime Nightshift o el endpoint Zetaris estén accesibles; haz los checks de Ajustes en tu máquina.

## Pruebas incluidas

La suite comprueba el proveedor Meterless, los contratos firmados y los bloqueos de Scout, la validación SQL allowlist, el registro SQLite y una ejecución multiagente de extremo a extremo con Nightshift/Zetaris simulados.

.env