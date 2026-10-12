# Verificacion documental

Modulo sin dependencias de Streamlit ni de base de datos. Recibe bytes de una imagen y devuelve `ResultadoVerificacion` mediante `verificar_documento` o `verificar_serial`. Los estados posibles son `verificado` y `en_revision`; el rechazo siempre corresponde a un humano.

El unico proveedor soportado es OpenRouter. Variables de entorno: `VLM_PROVIDER` (`openrouter`), `VLM_MODEL` (obligatoria, por ejemplo `qwen/qwen3.7-flash`), `OPENROUTER_API_KEY` o `VLM_API_KEY`, `VLM_BASE_URL` (por defecto `https://openrouter.ai/api/v1`), `UMBRAL_CONFIANZA` (0.90), `MAX_IMAGE_MB` (5), `VLM_TIMEOUT_S` (30) y `VLM_MAX_REINTENTOS` (1).