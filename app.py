from __future__ import annotations

import psycopg  # type: ignore[import-not-found]
import streamlit as st
from supabase import create_client  # type: ignore[import-not-found]

from core.auth import AuthService, Session, mfa_required
from core.config import get_settings
from core.db import backend_transaction, create_user_client
from core.permisos import puede_ver
from core.services.registros import (
    AltaPersona,
    Consentimiento,
    RegistroOrganizacion,
    RegistroPersona,
    alta_organizacion,
    alta_persona,
    enmascarar_documento,
    motivo_en_espanol,
)
from core.services.registros_db import BackendRecordsRepository
from core.services.registros_supabase import (
    SupabaseRecordsReader,
    SupabaseStorageUploader,
    SupabaseUASReader,
)
from core.services.uas import (
    NuevaAsignacion,
    NuevaInstalacion,
    NuevoUAS,
    crear_asignacion,
    crear_uas,
    instalar_componente,
    responder_asignacion,
)
from core.services.uas_db import BackendUASRepository
from core.verification.service import verificar_documento, verificar_serial
from ui.layout import render_header


def _login(auth: AuthService) -> Session | None:
    st.title("SUA - Sistema UTM Antioqueño")
    st.caption("Gestión de tráfico de drones para Medellín y Antioquia.")
    with st.form("login"):
        email = st.text_input("Correo electrónico")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Iniciar sesión", type="primary")
    if submitted:
        try:
            session = auth.sign_in(email, password)
            st.session_state["session"] = session
            st.rerun()
        except Exception:  # noqa: BLE001 - nunca se muestran detalles de Auth
            st.error("No fue posible iniciar sesión. Verifica tus credenciales.")
    return None


def _page(title: str, body: str) -> None:
    render_header(title)
    st.title(title)
    st.info(body)


def _mfa_gate(auth: AuthService) -> None:
    st.title("Autenticación multifactor")
    st.warning("Este rol requiere MFA (aal2) para acceder a SUA.")
    enrollment = st.session_state.get("mfa_enrollment")
    if not enrollment:
        if st.button("Inscribir autenticador TOTP", type="primary"):
            try:
                st.session_state["mfa_enrollment"] = auth.enroll_totp()
                st.rerun()
            except Exception:  # noqa: BLE001 - no se exponen detalles del proveedor
                st.error("No fue posible iniciar la inscripción MFA.")
        return
    if enrollment.get("uri"):
        st.code(enrollment["uri"], language="text")
    factor_id = enrollment.get("id") or enrollment.get("factor_id")
    with st.form("mfa_verify"):
        code = st.text_input("Código de seis dígitos", max_chars=6)
        submitted = st.form_submit_button("Verificar MFA", type="primary")
    if submitted and factor_id:
        try:
            challenge_id = auth.challenge_totp(str(factor_id))
            st.session_state["session"] = auth.verify_totp(str(factor_id), challenge_id, code)
            st.session_state.pop("mfa_enrollment", None)
            st.rerun()
        except Exception:  # noqa: BLE001 - no se exponen detalles del proveedor
            st.error("El código MFA no es válido o la inscripción expiró.")


def _state_badge(state: str | None) -> None:
    colors = {
        "vigente": "green",
        "operativa": "green",
        "verificado": "green",
        "en_revision": "orange",
        "pendiente": "orange",
        "suspendido": "red",
        "rechazado": "red",
    }
    color = colors.get(state or "", "gray")
    st.badge((state or "sin estado").replace("_", " ").title(), color=color)  # type: ignore[arg-type]


def _show_person_sheet(reader: SupabaseRecordsReader, kind: str, record_id: str) -> None:
    record = reader.get_person(kind, record_id)
    if not record:
        st.info("No se encontró la ficha.")
        return
    st.subheader(f"{record.get('nombres', '')} {record.get('apellidos', '')}".strip())
    st.write(f"Documento: {enmascarar_documento(record.get('documento_numero', ''))}")
    st.write(f"Correo: {record.get('correo_contacto') or 'No registrado'}")
    _state_badge(record.get("estado"))
    if kind == "pilotos":
        st.markdown("**Vínculos con organizaciones**")
        links = reader.links_for_pilot(record_id)
        st.dataframe(
            [
                {
                    "Organización": (link.get("organizaciones") or {}).get("razon_social", "Sin nombre"),
                    "Desde": link.get("vigente_desde"),
                    "Hasta": link.get("vigente_hasta") or "Vigente",
                    "Estado": link.get("estado", "").replace("_", " ").title(),
                }
                for link in links
            ],
            hide_index=True,
            use_container_width=True,
        ) if links else st.info("Sin vínculos registrados.")
    st.markdown("**Historial de verificaciones**")
    verifications = reader.verifications_for("piloto" if kind == "pilotos" else "tecnico", record_id)
    st.dataframe(
        [
            {
                "Tipo": item.get("tipo_documento"),
                "Estado": item.get("estado", "").replace("_", " ").title(),
                "Confianza": f"{float(item['confianza']):.0%}" if item.get("confianza") is not None else "No disponible",
                "Fecha": item.get("creado_en"),
            }
            for item in verifications
        ],
        hide_index=True,
        use_container_width=True,
    ) if verifications else st.info("Sin verificaciones registradas.")
    st.markdown("**Consentimientos**")
    consents = reader.consents_for("piloto" if kind == "pilotos" else "tecnico", record_id)
    st.dataframe(
        [
            {
                "Versión": item.get("texto_version"),
                "Finalidad": item.get("finalidad"),
                "Aceptado": item.get("aceptado_en"),
                "Revocado": item.get("revocado_en") or "Vigente",
            }
            for item in consents
        ],
        hide_index=True,
        use_container_width=True,
    ) if consents else st.info("Sin consentimientos registrados.")
    for consent in consents:
        if consent.get("revocado_en") is None and st.button(
            "Revocar consentimiento",
            key=f"revoke_consent_{kind}_{record_id}_{consent['id']}",
        ):
            reader.revoke_consent(
                "piloto" if kind == "pilotos" else "tecnico",
                record_id,
                consent["id"],
            )
            st.success("Consentimiento revocado.")
            st.rerun()


def _show_organization_sheet(reader: SupabaseRecordsReader, record_id: str) -> None:
    record = reader.get_organization(record_id)
    if not record:
        st.info("No se encontró la ficha.")
        return
    st.subheader(record.get("razon_social", "Organización"))
    st.write(f"NIT: {record.get('nit') or 'No registrado'}")
    st.write(f"Correo: {record.get('correo_contacto') or 'No registrado'}")
    _state_badge(record.get("estado"))


def _new_uas_form(session: Session, reader: SupabaseUASReader) -> None:
    settings = get_settings()
    organizations = reader.organizations()
    if not organizations:
        st.info("Sin organizaciones disponibles.")
        return
    organization_options = {item["razon_social"]: item["id"] for item in organizations}
    with st.form("new_uas"):
        registration = st.text_input("Matrícula")
        serial = st.text_input("Número de serie")
        manufacturer = st.text_input("Fabricante")
        model = st.text_input("Modelo")
        owner_name = st.selectbox("Organización propietaria", list(organization_options))
        observations = st.text_area("Observaciones")
        plate = st.file_uploader("Foto de placa/serial (opcional)", type=["jpg", "jpeg", "png", "webp"])
        save = st.form_submit_button("Guardar UAS")
    if not save:
        return
    result = None
    if plate is not None:
        result = verificar_serial(plate.getvalue(), plate.type or "image/jpeg", serial.strip())
        st.info(
            f"Serial: {'verificado' if result.estado == 'verificado' else 'en revisión'}."
        )
    try:
        with backend_transaction(session.user_id, session.app_role, "uas.alta", settings) as cursor:
            uas = crear_uas(
                NuevoUAS(
                    matricula=registration.strip(),
                    numero_serie=serial.strip(),
                    fabricante=manufacturer.strip() or None,
                    modelo=model.strip() or None,
                    propietario_id=organization_options[owner_name],
                    observaciones=observations.strip() or None,
                ),
                BackendUASRepository(cursor),
            )
        if plate is not None and result is not None:
            path = f"{session.user_id}/{uas['id']}"
            uploader = SupabaseStorageUploader(
                create_user_client(session.access_token, settings),
                settings.documentos_bucket,
            )
            uploader.upload(path, plate.getvalue(), plate.type or "image/jpeg")
            with backend_transaction(
                session.user_id,
                session.app_role,
                "uas.verificacion_serial",
                settings,
            ) as cursor:
                BackendUASRepository(cursor).create_serial_verification(
                    str(uas["id"]),
                    path,
                    result,
                )
        st.success("UAS creado en revisión.")
        if result is not None and result.estado != "verificado":
            st.warning("La placa/serial quedó en revisión humana.")
    except Exception:  # noqa: BLE001 - no se muestran SQL ni trazas
        st.error("No fue posible guardar el UAS. Verifica los datos e inténtalo de nuevo.")


def _uas_sheet(session: Session, reader: SupabaseUASReader, uas_id: str) -> None:
    settings = get_settings()
    uas = reader.get_uas(uas_id)
    if not uas:
        st.info("No se encontró la ficha del UAS.")
        return
    st.subheader(uas["matricula"])
    st.write(f"Serie: {uas['numero_serie']}")
    st.write(f"{uas.get('fabricante') or ''} {uas.get('modelo') or ''}".strip())
    _state_badge(uas.get("estado"))
    tabs = st.tabs(["Datos", "Asignaciones", "Componentes", "Métricas"])
    with tabs[0]:
        st.write(uas.get("observaciones") or "Sin observaciones.")
    with tabs[1]:
        assignments = reader.assignments(uas_id)
        if not assignments:
            st.info("Sin asignaciones.")
        for assignment in assignments:
            organization = (assignment.get("organizaciones") or {}).get("razon_social", "Sin organización")
            st.write(
                f"{organization} · {assignment['tipo']} · "
                f"{assignment['vigente_desde']} - {assignment.get('vigente_hasta') or 'vigente'}"
            )
            _state_badge(assignment.get("estado"))
            if assignment.get("estado") == "pendiente" and st.button(
                "Confirmar como propietario",
                key=f"confirm_assignment_{assignment['id']}",
            ):
                try:
                    actor_org = st.session_state.get("organization_id", "")
                    with backend_transaction(
                        session.user_id,
                        session.app_role,
                        "uas.confirmar_asignacion",
                        settings,
                    ) as cursor:
                        responder_asignacion(
                            assignment["id"],
                            assignment,
                            uas,
                            "confirmada",
                            actor_org,
                            BackendUASRepository(cursor),
                            actor_id=session.user_id,
                        )
                    st.success("Asignación confirmada.")
                    st.rerun()
                except (ValueError, KeyError, psycopg.Error):
                    st.error("No tienes permiso para confirmar esta asignación.")
        with st.expander("Nueva asignación"):
            organizations = reader.organizations()
            if organizations:
                options = {item["razon_social"]: item["id"] for item in organizations}
                selected = st.selectbox("Operador", list(options), key=f"assignment_org_{uas_id}")
                assignment_type = st.selectbox("Tipo", ["propio", "alquiler", "prestamo"], key=f"assignment_type_{uas_id}")
                starts = st.date_input("Desde", key=f"assignment_start_{uas_id}")
                ends = st.date_input("Hasta (opcional)", value=None, key=f"assignment_end_{uas_id}")
                if st.button("Crear asignación", key=f"create_assignment_{uas_id}"):
                    try:
                        with backend_transaction(session.user_id, session.app_role, "uas.asignacion", settings) as cursor:
                            crear_asignacion(
                                NuevaAsignacion(
                                    uas_id=uas_id,
                                    organizacion_id=options[selected],
                                    tipo=assignment_type,
                                    vigente_desde=starts,
                                    vigente_hasta=ends,
                                ),
                                BackendUASRepository(cursor),
                            )
                        st.success("Asignación creada pendiente de confirmación.")
                        st.rerun()
                    except (ValueError, KeyError, psycopg.Error):
                        st.error("No fue posible crear la asignación. Puede existir un solape.")
    with tabs[2]:
        components = reader.components(uas_id)
        catalog = reader.components_catalog()
        current = [item for item in components if item.get("retirado_en") is None]
        history = [item for item in components if item.get("retirado_en") is not None]
        st.write("Instalados actualmente")
        st.dataframe(
            [
                {
                    "Serie": (item.get("componentes") or {}).get("numero_serie"),
                    "Tipo": (item.get("componentes") or {}).get("tipo"),
                    "Instalado": item.get("instalado_en"),
                }
                for item in current
            ],
            hide_index=True,
        ) if current else st.info("Sin componentes instalados.")
        for installation in current:
            with st.expander(
                f"Retirar {(installation.get('componentes') or {}).get('numero_serie', 'componente')}"
            ):
                removed_at = st.text_input(
                    "Fecha y hora de retiro (UTC)",
                    key=f"removed_at_{installation['id']}",
                )
                reason = st.text_input("Motivo de retiro", key=f"remove_reason_{installation['id']}")
                if st.button("Retirar", key=f"remove_{installation['id']}"):
                    if not removed_at.strip() or not reason.strip():
                        st.error("La fecha y el motivo de retiro son obligatorios.")
                    else:
                        try:
                            with backend_transaction(
                                session.user_id,
                                session.app_role,
                                "uas.retirar_componente",
                                settings,
                            ) as cursor:
                                BackendUASRepository(cursor).remove_component(
                                    installation["id"],
                                    removed_at.strip(),
                                    reason.strip(),
                                )
                            st.success("Componente retirado.")
                            st.rerun()
                        except (ValueError, KeyError, psycopg.Error):
                            st.error("No fue posible retirar el componente.")
        st.write("Historial")
        st.dataframe(history, hide_index=True) if history else st.info("Sin historial.")
        with st.expander("Instalar componente"):
            if catalog:
                component_options = {
                    f"{item['numero_serie']} ({item['tipo']})": item["id"] for item in catalog
                }
                selected_component = st.selectbox(
                    "Componente",
                    list(component_options),
                    key=f"component_{uas_id}",
                )
                installed_at = st.text_input(
                    "Fecha y hora de instalación (UTC)",
                    key=f"installed_at_{uas_id}",
                )
                if st.button("Instalar", key=f"install_{uas_id}"):
                    component = reader.component(component_options[selected_component])
                    if component is None:
                        st.error("No se encontró el componente.")
                    else:
                        try:
                            with backend_transaction(
                                session.user_id,
                                session.app_role,
                                "uas.instalar_componente",
                                settings,
                            ) as cursor:
                                instalar_componente(
                                    NuevaInstalacion(
                                        componente_id=component["id"],
                                        uas_id=uas_id,
                                        instalado_en=installed_at.strip(),
                                        motivo=None,
                                    ),
                                    component,
                                    st.session_state.get("organization_id", ""),
                                    BackendUASRepository(cursor),
                                )
                            st.success("Componente instalado.")
                            st.rerun()
                        except (ValueError, KeyError, psycopg.Error):
                            st.error("No fue posible instalar el componente. Puede estar instalado en otro dron.")
            else:
                st.info("No hay componentes disponibles.")
        with st.expander("Alta de componente"):
            component_type = st.selectbox(
                "Tipo de componente",
                ["bateria", "motor", "inversor", "actuador", "computador_vuelo", "helice", "gimbal", "otro"],
                key=f"component_type_{uas_id}",
            )
            component_serial = st.text_input("Número de serie", key=f"component_serial_{uas_id}")
            component_owner = st.text_input(
                "Organización propietaria (ID)",
                value=st.session_state.get("organization_id", ""),
                key=f"component_owner_{uas_id}",
            )
            if st.button("Crear componente", key=f"create_component_{uas_id}"):
                if not component_serial.strip() or not component_owner.strip():
                    st.error("El serial y la organización propietaria son obligatorios.")
                else:
                    try:
                        with backend_transaction(
                            session.user_id,
                            session.app_role,
                            "uas.alta_componente",
                            settings,
                        ) as cursor:
                            BackendUASRepository(cursor).create_component(
                                component_serial.strip(),
                                component_type,
                                component_owner.strip(),
                            )
                        st.success("Componente creado.")
                        st.rerun()
                    except (ValueError, KeyError, psycopg.Error):
                        st.error("No fue posible crear el componente.")
    with tabs[3]:
        metrics = reader.metrics(uas_id)
        if metrics:
            st.metric("Horas de vuelo", metrics.get("horas_vuelo", 0))
            st.metric("Ciclos acumulados", metrics.get("ciclos", 0))
        else:
            st.info("Sin métricas disponibles.")


def _uas_page(session: Session) -> None:
    settings = get_settings()
    reader = SupabaseUASReader(create_user_client(session.access_token, settings))
    render_header("UAS")
    st.title("Registro de UAS")
    if st.button("+ Nuevo registro - UAS"):
        st.session_state["uas_new"] = True
    records = reader.list_uas()
    if not records:
        st.info("Sin resultados.")
    for uas in records:
        columns = st.columns([1.5, 2, 1, 1])
        columns[0].write(uas["matricula"])
        columns[1].write(f"{uas.get('fabricante') or ''} {uas.get('modelo') or ''}".strip())
        with columns[2]:
            _state_badge(uas.get("estado"))
        if columns[3].button("Ver ficha", key=f"uas_sheet_{uas['id']}"):
            st.session_state["uas_sheet"] = uas["id"]
    if st.session_state.get("uas_new"):
        with st.expander("Nuevo registro - UAS", expanded=True):
            _new_uas_form(session, reader)
    if st.session_state.get("uas_sheet"):
        with st.expander("Ficha de UAS", expanded=True):
            _uas_sheet(session, reader, st.session_state["uas_sheet"])


def _new_person_dialog(session: Session, kind: str) -> None:
    settings = get_settings()
    title = "Nuevo piloto" if kind == "piloto" else "Nuevo técnico"
    st.subheader(title)
    with st.form(f"new_{kind}"):
        document_type = st.selectbox("Tipo de documento", ["CC", "CE", "PA", "TI", "OTRO"])
        document_number = st.text_input("Número de documento")
        image = st.file_uploader("Imagen del documento", type=["jpg", "jpeg", "png", "webp"])
        consent = st.checkbox(
            "Acepto el tratamiento de mis datos y que la imagen se procese con un proveedor externo."
        )
        verify = st.form_submit_button("Verificar documento")
    if verify:
        if not document_number.strip() or image is None or not consent:
            st.error("Completa el documento, la imagen y el consentimiento antes de verificar.")
            return
        result = verificar_documento(
            image.getvalue(),
            image.type or "image/jpeg",
            document_type,
            document_number.strip(),
        )
        st.session_state["records_pending_verification"] = (result, image.getvalue(), image.type or "image/jpeg")
        st.session_state["records_pending_kind"] = kind
        st.rerun()

    pending = st.session_state.get("records_pending_verification")
    if not pending or st.session_state.get("records_pending_kind") != kind:
        return
    result, image_bytes, mime = pending
    st.info(f"{'Verificado' if result.estado == 'verificado' else 'En revisión'}: {motivo_en_espanol(result.motivo)}")
    with st.form(f"save_{kind}"):
        names = st.text_input("Nombres", value=result.nombres_extraidos or "")
        surnames = st.text_input("Apellidos", value=result.apellidos_extraidos or "")
        email = st.text_input("Correo")
        license_number = st.text_input("Número de licencia")
        license_expiry = st.date_input("Vencimiento de licencia", value=None)
        observations = st.text_area("Observaciones")
        save = st.form_submit_button("Guardar")
    if save:
        data = AltaPersona(
            persona=RegistroPersona(
                tipo=kind,
                documento_tipo=document_type,
                documento_numero=document_number.strip(),
                nombres=names.strip(),
                apellidos=surnames.strip(),
                correo=email.strip(),
                licencia_numero=license_number.strip() or None,
                licencia_vence=license_expiry,
                observaciones=observations.strip() or None,
            ),
            consentimiento=Consentimiento(
                version="REGISTROS-2026-01",
                texto="Consentimiento para verificación de identidad; la imagen se procesa con un proveedor externo.",
            ),
            valor_ingresado=document_number.strip(),
            imagen=image_bytes,
            mime=mime,
            resultado=result,
        )
        try:
            with backend_transaction(session.user_id, session.app_role, "registros.alta_persona", settings) as cursor:
                profile = alta_persona(
                    session.user_id,
                    data,
                    BackendRecordsRepository(cursor),
                    SupabaseStorageUploader(create_user_client(session.access_token, settings), settings.documentos_bucket),
                )
            st.session_state.pop("records_pending_verification", None)
            st.success(f"Registro guardado: {profile['nombres']} {profile['apellidos']}.")
        except Exception:  # noqa: BLE001 - se traduce a un mensaje sin PII ni SQL
            st.error("No fue posible guardar el registro. Verifica los datos e inténtalo de nuevo.")


def _new_organization_form(session: Session, kind: str) -> None:
    settings = get_settings()
    with st.form(f"new_organization_{kind}"):
        legal_name = st.text_input("Razón social")
        nit = st.text_input("NIT")
        email = st.text_input("Correo")
        observations = st.text_area("Observaciones")
        legal_document = st.file_uploader(
            "Documento legal (opcional)",
            type=["jpg", "jpeg", "png", "pdf"],
            key=f"legal_document_{kind}",
        )
        consent = st.checkbox(
            "Acepto el tratamiento de la información y el procesamiento externo de la imagen."
        )
        save = st.form_submit_button("Guardar")
    if not save:
        return
    if not legal_name.strip() or not nit.strip():
        st.error("La razón social y el NIT son obligatorios.")
        return
    if legal_document is not None and not consent:
        st.error("Debes aceptar el consentimiento antes de subir un documento legal.")
        return
    try:
        with backend_transaction(session.user_id, session.app_role, "registros.alta_organizacion", settings) as cursor:
            alta_organizacion(
                RegistroOrganizacion(
                    tipo=kind,
                    razon_social=legal_name.strip(),
                    nit=nit.strip(),
                    correo=email.strip() or None,
                    observaciones=observations.strip() or None,
                ),
                BackendRecordsRepository(cursor),
                actor_id=session.user_id,
                storage=(
                    SupabaseStorageUploader(
                        create_user_client(session.access_token, settings),
                        settings.documentos_bucket,
                    )
                    if legal_document is not None
                    else None
                ),
                legal_document=legal_document.getvalue() if legal_document is not None else None,
                legal_mime=legal_document.type if legal_document is not None else None,
                consent=(
                    Consentimiento(
                        version="REGISTROS-2026-01",
                        texto="Consentimiento para documento legal; la imagen se procesa con un proveedor externo.",
                    )
                    if legal_document is not None
                    else None
                ),
            )
        st.success("Organización creada en revisión.")
    except Exception:  # noqa: BLE001 - se traduce a un mensaje sin SQL ni PII
        st.error("No fue posible guardar la organización. Verifica los datos e inténtalo de nuevo.")


def _records_page(session: Session) -> None:
    settings = get_settings()
    reader = SupabaseRecordsReader(create_user_client(session.access_token, settings))
    render_header("Registros")
    st.title("Registros")
    tabs = st.tabs(["Pilotos", "Técnicos", "Compañías", "Escuelas"])
    for tab, kind in zip(tabs, ["pilotos", "tecnicos", "empresa", "escuela"]):
        with tab:
            if st.button("+ Nuevo registro", key=f"new_{kind}"):
                st.session_state["records_new_kind"] = kind
            if kind in {"pilotos", "tecnicos"}:
                records = reader.list_people(kind)
            else:
                records = reader.list_organizations(kind)
                if st.session_state.get("records_new_kind") == kind:
                    _new_organization_form(session, kind)
            if not records:
                st.info("Sin resultados.")
            for record in records:
                identifier = (
                    enmascarar_documento(record["documento_numero"])
                    if kind in {"pilotos", "tecnicos"}
                    else record.get("nit", "")
                )
                name = (
                    f"{record.get('nombres', '')} {record.get('apellidos', '')}".strip()
                    if kind in {"pilotos", "tecnicos"}
                    else record.get("razon_social", "")
                )
                columns = st.columns([1.2, 2, 1, 1])
                columns[0].write(identifier)
                columns[1].write(name)
                with columns[2]:
                    _state_badge(record.get("estado_verificacion") or record.get("estado"))
                if columns[3].button("Ver ficha", key=f"sheet_{kind}_{record['id']}"):
                    st.session_state["records_sheet"] = (kind, record["id"])
    new_kind = st.session_state.get("records_new_kind")
    if new_kind in {"piloto", "tecnico"}:
        with st.expander("Nuevo registro", expanded=True):
            _new_person_dialog(session, new_kind)
    sheet = st.session_state.get("records_sheet")
    if sheet and sheet[0] in {"pilotos", "tecnicos"}:
        with st.expander("Ficha", expanded=True):
            _show_person_sheet(reader, sheet[0], sheet[1])
    elif sheet and sheet[0] in {"empresa", "escuela"}:
        with st.expander("Ficha", expanded=True):
            _show_organization_sheet(reader, sheet[1])


def main() -> None:
    settings = get_settings()
    auth = AuthService(create_client(settings.supabase_url, settings.supabase_anon_key), settings=settings)
    session = st.session_state.get("session")
    if not isinstance(session, Session):
        _login(auth)
        st.page_link("pages/registro_cuenta.py", label="Crear una cuenta")
        st.page_link("pages/ayuda.py", label="Ayuda")
        return
    if mfa_required(session, auth.current_aal()):
        _mfa_gate(auth)
        return
    if st.sidebar.button("Cerrar sesión"):
        auth.sign_out()
        st.session_state.clear()
        st.rerun()

    role = session.app_role
    pages = {
        "Control UTM": lambda: _page("Control UTM", "Panel operativo en construcción."),
        "Planes de vuelo": lambda: _page("Planes de vuelo", "Los planes serán validados por la base de datos."),
        "UAS": lambda: _uas_page(session),
        "Registros": lambda: _records_page(session),
        "Mantenimiento": lambda: _page("Mantenimiento", "Historial de mantenimiento."),
        "Ayuda": lambda: _page("Ayuda", "Consulta la documentación de SUA."),
        "Acerca": lambda: _page("Acerca", "Sistema UTM Antioqueño."),
        "Aprobaciones": lambda: _page("Aprobaciones", "Bandeja de aprobaciones para autoridades."),
        "Gestor GIS": lambda: _page("Gestor GIS", "Gestión de zonas y geometrías."),
        "Objetos GIS": lambda: _page("Objetos GIS", "Objetos geográficos operativos."),
        "Cuentas": lambda: _page("Cuentas", "Gestión administrativa de cuentas."),
        "Auditoría": lambda: _page("Auditoría", "Consulta de auditoría."),
        "Verificaciones": lambda: _page("Verificaciones", "Revisión de identidad."),
    }
    allowed = {name: callback for name, callback in pages.items() if puede_ver(role, name)}
    if not allowed:
        st.error("Tu cuenta no tiene un perfil operativo asignado.")
        return
    selected = st.sidebar.radio("Módulo", list(allowed))
    allowed[selected]()


if __name__ == "__main__":
    main()
