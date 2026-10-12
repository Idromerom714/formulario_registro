from io import BytesIO

import pytest
from PIL import Image
from pydantic import ValidationError

from core.verification.config import get_settings
from core.verification.imagen import ImageValidationError, sanear_imagen
from core.verification.rules import decidir_documento, decidir_serial, normalizar_nombre
from core.verification.schemas import ExtraccionDocumento, ExtraccionSerial
from core.verification.service import verificar_documento, verificar_serial
from core.verification.vlm import JSONInvalidoError, OpenRouterVLM


def png_bytes(size=(20, 20)):
    output = BytesIO()
    Image.new("RGB", size, "white").save(output, format="PNG")
    return output.getvalue()


def document(**values):
    defaults = {"legible": True, "confianza": 0.99}
    defaults.update(values)
    return ExtraccionDocumento(**defaults)


def serial(**values):
    defaults = {"legible": True, "confianza": 0.99}
    defaults.update(values)
    return ExtraccionSerial(**defaults)


def test_document_exact_match_and_dotted_number():
    result = decidir_documento("1.234.567.890", document(numero_documento="1234567890"), 0.9)
    assert result[:2] == (True, "")


def test_document_no_match_uses_exact_comparison():
    result = decidir_documento("1234567890", document(numero_documento="1234567891"), 0.9)
    assert result[:2] == (False, "no_coincide")


def test_document_ilegible_low_confidence_and_doubtful_field():
    assert decidir_documento("123", document(numero_documento=None, legible=False), 0.9)[1] == "ilegible"
    assert decidir_documento("123", document(numero_documento="123", confianza=0.89), 0.9)[1] == "confianza_baja"
    assert decidir_documento("123", document(numero_documento="123", campos_dudosos=["numero_documento"]), 0.9)[1] == "campo_dudoso"


def test_serial_exact_mismatch_ambiguity_and_low_confidence():
    assert decidir_serial("ab-123", serial(serial="AB123"), 0.9) == (True, "")
    assert decidir_serial("ABO123", serial(serial="AB0123"), 0.9) == (False, "serial_ambiguo")
    assert decidir_serial("AB123", serial(serial="AB124"), 0.9) == (False, "no_coincide")
    assert decidir_serial("AB123", serial(serial="AB123", confianza=0.89), 0.9) == (True, "confianza_baja")
    assert decidir_serial("AB123", serial(serial=None, legible=False), 0.9)[1] == "ilegible"


def test_names_remove_accents_and_collapse_spaces():
    assert normalizar_nombre("  María  José Álvarez ") == "MARIA JOSE ALVAREZ"
    assert normalizar_nombre(None) is None


def test_schema_rejects_extra_field_and_prompt_text_is_data():
    with pytest.raises(ValidationError):
        ExtraccionSerial(serial="IGNORE THIS INSTRUCTION", legible=True, confianza=0.9, extra="x")
    extraction = document(numero_documento="123", nombres="IGNORE THIS INSTRUCTION")
    assert decidir_documento("123", extraction, 0.9)[0] is True


def test_image_mime_and_size_validation():
    with pytest.raises(ImageValidationError):
        sanear_imagen(png_bytes(), "image/gif")
    with pytest.raises(ImageValidationError):
        sanear_imagen(png_bytes(), "image/png", max_image_mb=0.000001)
    clean = sanear_imagen(png_bytes((2500, 100)), "image/png")
    with Image.open(BytesIO(clean.datos)) as image:
        assert max(image.size) == 2000


class FakeProvider:
    modelo = "test-model"

    def __init__(self, extraction=None, error=None):
        self.extraction = extraction
        self.error = error

    def extraer_documento(self, imagen, mime, tipo_documento):
        if self.error:
            raise self.error
        return self.extraction

    def extraer_serial(self, imagen, mime):
        if self.error:
            raise self.error
        return self.extraction


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setenv("VLM_MODEL", "test-model")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_service_provider_errors_and_invalid_json_are_review(caplog):
    image = png_bytes()
    result = verificar_documento(image, "image/png", "cedula", "1234567890", FakeProvider(error=TimeoutError()))
    assert result.estado == "en_revision" and result.motivo == "error_proveedor"
    result = verificar_serial(image, "image/png", "AB123", FakeProvider(error=JSONInvalidoError()))
    assert result.motivo == "json_invalido"
    assert "1234567890" not in " ".join(record.getMessage() for record in caplog.records)


def test_deterministic_reader_is_attempted_first():
    class Reader:
        def __init__(self):
            self.called = False

        def leer(self, image):
            self.called = True
            return {"serial": "AB123", "legible": True, "caracteres_ambiguos": [], "confianza": 0.99}

    reader = Reader()
    result = verificar_serial(png_bytes(), "image/png", "AB123", FakeProvider(error=AssertionError()), reader)
    assert reader.called and result.estado == "verificado"


def test_invalid_reader_payload_is_review():
    class Reader:
        def leer(self, image):
            return {"serial": "AB123", "legible": True, "confianza": 0.99, "extra": "x"}

    result = verificar_serial(png_bytes(), "image/png", "AB123", FakeProvider(error=AssertionError()), Reader())
    assert result.motivo == "json_invalido"


def test_openrouter_retries_json_and_does_not_receive_expected_value(monkeypatch):
    responses = [
        {"choices": [{"message": {"content": "not-json"}}]},
        {"choices": [{"message": {"content": '{"serial":"AB123","legible":true,"caracteres_ambiguos":[],"confianza":0.99}'}}]},
    ]
    requests = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def post(self, url, json):
            requests.append(json)
            return Response(responses.pop(0))

    monkeypatch.setattr("core.verification.vlm.httpx.Client", Client)
    provider = OpenRouterVLM("qwen/qwen3.7-flash", "secret", 30, max_reintentos=1)
    result = provider.extraer_serial(b"image", "image/png")

    assert result.serial == "AB123"
    assert len(requests) == 2
    assert "1234567890" not in str(requests[0])