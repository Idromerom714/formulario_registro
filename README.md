# Formulario de Registro (MVP de prueba)

Aplicación en **Streamlit** para registrar usuarios solo después de validar visualmente un identificador (documento o serial) desde una imagen.

## Estado actual

Este repositorio contiene un **MVP funcional de prueba** con:

- Verificación de código/serial mediante modelo multimodal (OpenRouter).
- Captura por cámara o carga de imagen.
- Comparación tolerante del código detectado (normalización + distancia de Levenshtein).
- Bloqueo del formulario hasta validar identidad.
- Persistencia local en SQLite (`registros.db`) de registros verificados.

## Flujo del MVP

1. Seleccionar tipo de documento/equipo.
2. Ingresar el número/serial esperado.
3. Tomar foto o subir imagen.
4. Ejecutar verificación.
5. Si coincide, se habilita el formulario de registro.
6. Al completar datos obligatorios, se guarda el registro en SQLite.

## Stack actual

- Python 3.10+
- Streamlit
- httpx
- pydantic
- python-dotenv
- SQLite (incluido con Python)

## Instalación

```bash
pip install -r requirements.txt
```

## Configuración

Crear un archivo `.env` en la raíz con:

```env
OPENROUTER_API_KEY=tu_api_key
```

> Sin esta variable, la verificación de imagen no funciona.

## Ejecución

```bash
streamlit run app.py
```

Luego abrir en navegador la URL local que muestra Streamlit (normalmente `http://localhost:8501`).

## Datos almacenados

Se crea/usa una base `registros.db` con una tabla `registros` que guarda:

- timestamp
- tipo de documento
- serial validado
- nombre
- email
- estado de verificación (`VERIFICADO`)

## Alcance y limitaciones del MVP

- Proyecto orientado a validación de concepto.
- No incluye autenticación de usuarios.
- No incluye panel de administración ni exportación de datos.
- El campo “Notas” existe en UI pero no se persiste en base de datos en esta versión.
