# Formulario de registro (MVP de prueba)

Aplicación en **Streamlit** para registrar usuarios solo después de validar visualmente un identificador (documento o serial) desde una imagen.

## Estado actual del MVP

Este MVP ya permite:

- Seleccionar tipo de identificador:
  - Cédula de Ciudadanía
  - Dron (Serial S/N)
  - Batería/Componente
- Ingresar el código esperado.
- Tomar foto con cámara o subir imagen.
- Enviar la imagen a un modelo VLM vía **OpenRouter** para extraer el código.
- Comparar el código detectado con el esperado (comparación normalizada y tolerancia mínima de error).
- Desbloquear el formulario de registro solo si la verificación es exitosa.
- Guardar el registro verificado en una base local **SQLite** (`registros.db`).

## Stack usado

- Python
- Streamlit
- httpx
- pydantic
- python-dotenv
- SQLite (incluido en Python)

## Requisitos

- Python 3.10+ (recomendado)
- Variable de entorno:
  - `OPENROUTER_API_KEY`

## Instalación y ejecución local

1. Clona el repositorio.
2. Crea y activa un entorno virtual.
3. Instala dependencias:

```bash
pip install -r requirements.txt
```

4. Configura la variable de entorno (ejemplo con `.env`):

```env
OPENROUTER_API_KEY=tu_api_key
```

5. Ejecuta la app:

```bash
streamlit run app.py
```

## Flujo funcional actual

1. El usuario selecciona tipo de documento/equipo.
2. Escribe número/serial esperado.
3. Carga o captura una imagen.
4. Presiona **Verificar identificación**.
5. Si hay coincidencia, se habilita el formulario.
6. Completa nombre, correo y rol.
7. Se guarda un registro con estado `VERIFICADO`.

## Persistencia de datos

- Base de datos local: `registros.db`
- Tabla principal: `registros`
- Campos almacenados:
  - timestamp
  - tipo_doc
  - serial_validado
  - nombre
  - email
  - estado_verificacion

## Limitaciones actuales del MVP

- No hay autenticación ni gestión de usuarios.
- No existe panel para consultar/editar registros guardados.
- El campo `Notas` se captura en UI pero no se persiste en la base.
- La verificación depende de calidad de imagen y respuesta del modelo externo.
