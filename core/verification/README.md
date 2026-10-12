# Verificacion documental

Modulo sin dependencias de Streamlit ni de base de datos. Recibe bytes de una imagen y devuelve `ResultadoVerificacion` mediante `verificar_documento` o `verificar_serial`. Los estados posibles son `verificado` y `en_revision`; el rechazo siempre corresponde a un humano.

Variables de entorno: `VLM_PROVIDER` (por defecto `anthropic`), `VLM_MODEL` (obligatoria), `VLM_API_KEY`, `UMBRAL_CONFIANZA` (0.90), `MAX_IMAGE_MB` (5), `VLM_TIMEOUT_S` (30) y `VLM_MAX_REINTENTOS` (1).