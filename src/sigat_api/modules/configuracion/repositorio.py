"""Acceso a datos de configuración. Fuentes: v_lote_app, v_trampa_app, v_trampa_lote_vigente,
fn_lote_app(usua), fn_trampa_app(usua), fn_lote_que_contiene(punto, instante)."""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from sigat_api.compartido.errores import NoImplementado

# Las vistas de la aplicación (``v_lote_app``, ``v_trampa_app``) traen ya los nombres de campo
# que el móvil lee. Lo que no traen y el esquema exige se resuelve con estos joins:
#   * ``atrayente``          -> sigat.atrayente (el tipo de cebo no está en la vista)
#   * ``ubic_id``            -> v_trampa_lote_vigente (la ubicación vigente de la trampa)
#   * ``dentro_del_lote``    -> v_trampa_lote_vigente (comprobación espacial, RF-012)
_SELECT_TRAMPAS = """
SELECT v.*,
       a.atra_descripcion AS atrayente,
       vl.ubic_id,
       vl.dentro_del_lote,
       vl.lote_sin_geometria
  FROM {origen} v
  JOIN sigat.trampa t ON t.tram_id = v.tram_id
  LEFT JOIN sigat.atrayente a ON a.atra_id = t.atra_id
  LEFT JOIN sigat.v_trampa_lote_vigente vl ON vl.tram_id = v.tram_id
"""


class RepositorioConfiguracion:
    def __init__(self, con: AsyncConnection) -> None:
        self._con = con

    # predios
    async def predios_visibles(self, usua_id: int) -> list[dict[str, Any]]:
        raise NoImplementado("Predios visibles")

    async def predio(self, pred_id: int) -> dict[str, Any] | None:
        raise NoImplementado("Predio")

    async def actualizar_predio(self, pred_id: int, cambios: dict[str, Any]) -> None:
        """Fija pred_fecha_actualizacion y pred_tecnico_actualizacion_id según la BD."""
        raise NoImplementado("Actualizar predio")

    async def mapa_predio(self, pred_id: int, instante: datetime) -> dict[str, Any]:
        """ST_AsGeoJSON de predio, lote_geometria vigente en ``instante``, reticula_celda y ubicacion_trampa."""
        raise NoImplementado("Mapa del predio")

    # lotes
    async def lotes_visibles(self, usua_id: int, pred_id: int | None) -> list[dict[str, Any]]:
        """``SELECT * FROM fn_lote_app(:usua)`` (ya filtrado por fn_lotes_visibles).

        ``fn_lote_app`` ya aplica el permiso: el admin ve todos los lotes, el técnico solo los de
        sus actividades vigentes y el productor/agronomo los de sus predios. Aquí solo se acota por
        ``pred_id`` cuando el cliente lo pide.
        """
        filas = await self._con.execute(
            text(
                """
SELECT * FROM sigat.fn_lote_app(:usua)
 WHERE CAST(:pred_id AS integer) IS NULL OR pred_id = CAST(:pred_id AS integer)
 ORDER BY lote_id
"""
            ),
            {"usua": usua_id, "pred_id": pred_id},
        )
        return [dict(f) for f in filas.mappings()]

    async def lote(self, lote_id: int) -> dict[str, Any] | None:
        """Detalle de un lote: ``v_lote_app`` + las columnas de ``sigat.lote`` que solo pide el
        detalle (fechas, cultivo, variedad) + la versión vigente de la geometría (GeoJSON).

        La geometría vigente se toma con ``LATERAL``: la vista ``v_lote_app`` no la trae y hace
        falta un subplan que elija la versión más reciente que esté en vigor ahora.
        """
        fila = (
            (
                await self._con.execute(
                    text(
                        """
SELECT v.*,
       l.espc_id,
       l.vari_id,
       l.lote_fecha_plantacion,
       l.lote_fecha_registro,
       l.lote_fecha_baja,
       g.lotg_version AS geometria_version,
       CASE WHEN g.lotg_geom IS NULL THEN NULL ELSE ST_AsGeoJSON(g.lotg_geom) END AS geometria
  FROM sigat.v_lote_app v
  JOIN sigat.lote l ON l.lote_id = v.lote_id
  LEFT JOIN LATERAL (
       SELECT lotg_version, lotg_geom
         FROM sigat.lote_geometria
        WHERE lote_id = v.lote_id
          AND lotg_vigente_desde <= now()
          AND (lotg_vigente_hasta IS NULL OR lotg_vigente_hasta > now())
        ORDER BY lotg_version DESC
        LIMIT 1
  ) g ON true
 WHERE v.lote_id = :lote_id
"""
                    ),
                    {"lote_id": lote_id},
                )
            )
            .mappings()
            .first()
        )
        if fila is None:
            return None
        datos = dict(fila)
        if isinstance(datos.get("geometria"), str):
            datos["geometria"] = json.loads(datos["geometria"])
        return datos

    async def lote_visible(self, usua_id: int, lote_id: int) -> bool:
        """``lote_id IN (SELECT * FROM fn_lotes_visibles(:usua))``. Si no -> 404 (no 403, para no
        revelar que el lote existe pero es de otro usuario."""
        return bool(
            await self._con.scalar(
                text("SELECT EXISTS (SELECT 1 FROM sigat.fn_lotes_visibles(:usua) WHERE lote_id = :lote_id)"),
                {"usua": usua_id, "lote_id": lote_id},
            )
        )

    async def insertar_lote(self, pred_id: int, datos: dict[str, Any]) -> int:
        raise NoImplementado("Alta de lote")

    async def actualizar_lote(self, lote_id: int, cambios: dict[str, Any]) -> None:
        raise NoImplementado("Actualizar lote")

    async def versiones_geometria(self, lote_id: int) -> list[dict[str, Any]]:
        raise NoImplementado("Versiones de geometría")

    async def nueva_version_geometria(
        self, lote_id: int, geojson: str, desde: datetime, fuente: str, motivo: str
    ) -> int:
        """En una transacción: cierra la vigente (lotg_vigente_hasta = desde) e inserta la nueva.
        La BD valida geometría (fn_lote_geometria_valida) y no solape (EXCLUDE)."""
        raise NoImplementado("Nueva versión de geometría")

    # trampas
    async def trampas_visibles(
        self, usua_id: int, lote_id: int | None, pred_id: int | None
    ) -> list[dict[str, Any]]:
        """``fn_trampa_app(:usua)`` + v_trampa_lote_vigente.

        ``fn_trampa_app`` ya filtra por permiso: solo salen las trampas de los lotes que el actor
        puede ver (``fn_lotes_visibles``). ``lote_id`` y ``pred_id`` solo acotan el resultado.
        """
        filas = await self._con.execute(
            text(
                _SELECT_TRAMPAS.format(origen="sigat.fn_trampa_app(:usua)")
                + """
 WHERE (CAST(:lote_id AS integer) IS NULL OR v.lote_id = CAST(:lote_id AS integer))
   AND (CAST(:pred_id AS integer) IS NULL OR v.pred_id = CAST(:pred_id AS integer))
 ORDER BY v.tram_codigo
"""
            ),
            {"usua": usua_id, "lote_id": lote_id, "pred_id": pred_id},
        )
        return [dict(f) for f in filas.mappings()]

    async def trampa_por_id(self, usua_id: int, tram_id: int) -> dict[str, Any] | None:
        """Trampa por identificador, dentro de las visibles para el actor."""
        fila = (
            (
                await self._con.execute(
                    text(
                        _SELECT_TRAMPAS.format(origen="sigat.fn_trampa_app(:usua)")
                        + " WHERE v.tram_id = :tram_id"
                    ),
                    {"usua": usua_id, "tram_id": tram_id},
                )
            )
            .mappings()
            .first()
        )
        return dict(fila) if fila is not None else None

    async def trampa_por_codigo(self, tram_codigo: str) -> dict[str, Any] | None:
        """Busca por código ICA en TODO el catálogo, no solo en los lotes visibles del actor.

        RF-012 compara trampa–lote–ubicación y AVISA, no bloquea: el técnico tiene que poder
        validar la trampa que tiene delante aunque no sea la que tiene asignada. Si se filtrara
        por visibilidad, la pantalla de validación no podría mostrar nada.

        ``con_ubicacion_vigente`` distingue «el código existe» de «la trampa tiene ubicación
        vigente» (sin ubicación no hay coordenadas que comparar).
        """
        fila = (
            (
                await self._con.execute(
                    text(
                        """
SELECT t.tram_id,
       t.tram_codigo,
       v.tipo,
       v.lote_id,
       v.pred_id,
       v.longitud,
       v.latitud,
       v.celda,
       v.estado,
       v.ultima_lectura,
       v.ultima_lectura_especimenes,
       a.atra_descripcion AS atrayente,
       vl.ubic_id,
       vl.dentro_del_lote,
       vl.lote_sin_geometria,
       (v.tram_id IS NOT NULL) AS con_ubicacion_vigente
  FROM sigat.trampa t
  LEFT JOIN sigat.v_trampa_app v ON v.tram_id = t.tram_id
  LEFT JOIN sigat.atrayente a ON a.atra_id = t.atra_id
  LEFT JOIN sigat.v_trampa_lote_vigente vl ON vl.tram_id = t.tram_id
 WHERE t.tram_codigo = :codigo
"""
                    ),
                    {"codigo": tram_codigo},
                )
            )
            .mappings()
            .first()
        )
        return dict(fila) if fila is not None else None

    async def lote_que_contiene(self, lon: float, lat: float, instante: datetime) -> int | None:
        """``fn_lote_que_contiene(ST_SetSRID(ST_MakePoint(lon, lat), 4326), instante)``."""
        valor = await self._con.scalar(
            text("SELECT sigat.fn_lote_que_contiene(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :instante)"),
            {"lon": lon, "lat": lat, "instante": instante},
        )
        return int(valor) if valor is not None else None

    async def tipo_trampa(self, tipt_id: int) -> dict[str, Any] | None:
        """Tipo de trampa con la paridad que exige al número (RN-005). None si no existe."""
        fila = (
            (
                await self._con.execute(
                    text(
                        "SELECT tipt_id, tipt_descripcion, tipt_paridad FROM sigat.tipo_trampa"
                        " WHERE tipt_id = :tipt_id"
                    ),
                    {"tipt_id": tipt_id},
                )
            )
            .mappings()
            .first()
        )
        return dict(fila) if fila is not None else None

    async def existe_codigo_trampa(self, tram_codigo: str) -> bool:
        """El código ICA es único en todo el catálogo (``trampa_tram_codigo_key``)."""
        return bool(
            await self._con.scalar(
                text("SELECT EXISTS (SELECT 1 FROM sigat.trampa WHERE tram_codigo = :codigo)"),
                {"codigo": tram_codigo},
            )
        )

    async def predio_del_lote(self, lote_id: int) -> int | None:
        """``ubicacion_trampa.pred_id`` sale del lote (FK compuesta lote_id, pred_id)."""
        valor = await self._con.scalar(
            text("SELECT pred_id FROM sigat.lote WHERE lote_id = :lote_id"), {"lote_id": lote_id}
        )
        return int(valor) if valor is not None else None

    async def lote_activo_en(self, lote_id: int, fecha: date) -> bool:
        """El lote está activo entre ``lote_fecha_registro`` (inclusive) y ``lote_fecha_baja``
        (primer día inactivo, exclusivo), según la definición de la tabla ``lote``."""
        return bool(
            await self._con.scalar(
                text(
                    """
SELECT EXISTS (
       SELECT 1 FROM sigat.lote
        WHERE lote_id = :lote_id
          AND lote_fecha_registro <= :fecha
          AND (lote_fecha_baja IS NULL OR lote_fecha_baja > :fecha))
"""
                ),
                {"lote_id": lote_id, "fecha": fecha},
            )
        )

    async def distancia_minima_trampas(self, pred_id: int, fecha: date) -> int | None:
        """RN-004: ``prog_distancia_min_trampas_m`` del programa vigente en ``fecha``.

        Vigencia [desde, hasta). None si el predio no tiene programa vigente en esa fecha.
        """
        valor = await self._con.scalar(
            text(
                """
SELECT prog_distancia_min_trampas_m
  FROM sigat.programa_inspeccion
 WHERE pred_id = :pred_id
   AND prog_vigente_desde <= :fecha
   AND (prog_vigente_hasta IS NULL OR prog_vigente_hasta > :fecha)
"""
            ),
            {"pred_id": pred_id, "fecha": fecha},
        )
        return int(valor) if valor is not None else None

    async def trampas_cercanas(
        self,
        pred_id: int,
        lon: Decimal,
        lat: Decimal,
        fecha: date,
        distancia_m: int,
        excluir_tram_id: int | None = None,
    ) -> list[str]:
        """Códigos de las trampas del predio a menos de ``distancia_m`` del punto (RN-004).

        La BD no hace cumplir esta regla para trampas (solo para la retícula), por eso se consulta
        aquí. Cuenta las ubicaciones que siguen vigentes desde ``fecha``. La distancia se mide en
        metros sobre ``geography``. ``excluir_tram_id`` deja fuera a la propia trampa al reubicarla.
        """
        filas = await self._con.execute(
            text(
                """
SELECT t.tram_codigo
  FROM sigat.ubicacion_trampa u
  JOIN sigat.trampa t ON t.tram_id = u.tram_id
 WHERE u.pred_id = :pred_id
   AND (u.ubic_fecha_fin IS NULL OR u.ubic_fecha_fin > :fecha)
   AND (CAST(:excluir AS integer) IS NULL OR u.tram_id <> CAST(:excluir AS integer))
   AND ST_Distance(
         CAST(u.ubic_geom AS geography),
         CAST(ST_SetSRID(ST_MakePoint(CAST(:lon AS float8), CAST(:lat AS float8)), 4326) AS geography)
       ) < :distancia
 ORDER BY t.tram_codigo
"""
            ),
            {
                "pred_id": pred_id,
                "fecha": fecha,
                "excluir": excluir_tram_id,
                "lon": float(lon),
                "lat": float(lat),
                "distancia": distancia_m,
            },
        )
        return [str(f) for f in filas.scalars()]

    async def insertar_trampa(self, datos: dict[str, Any], ubicacion: dict[str, Any]) -> int:
        """trampa + ubicacion_trampa en una transacción (fn_trampa_valida, fn_ubicacion_trampa_valida).

        El SAVEPOINT garantiza que no quede una trampa sin ubicación si la BD rechaza la segunda
        fila. La trampa nace en estado ``activo`` con la fecha de hoy en la zona del predio (ADR-10).
        """
        async with self._con.begin_nested():
            tram_id = await self._con.scalar(
                text(
                    """
INSERT INTO sigat.trampa (tram_codigo, tipt_id, atra_id, esta_id, tram_fecha_registro,
                          tram_tecnico_registro_id)
SELECT :tram_codigo, :tipt_id, :atra_id, e.esta_id,
       CAST(now() AT TIME ZONE p.pred_zona_horaria AS date), :tram_tecnico_registro_id
  FROM sigat.estado_registro e
  JOIN sigat.predio p ON p.pred_id = :pred_id
 WHERE e.esta_descripcion = 'activo'
RETURNING tram_id
"""
                ),
                {**datos, "pred_id": ubicacion["pred_id"]},
            )
            if tram_id is None:
                raise RuntimeError("Falta el estado 'activo' en estado_registro o el predio no existe")
            await self._con.execute(
                text(
                    """
INSERT INTO sigat.ubicacion_trampa (tram_id, pred_id, lote_id, ubic_fecha, tecn_id, vigi_id, ruta_id,
                                    retc_id, loca_id, arbo_id, ubic_long, ubic_lat, ubic_alt,
                                    ubic_referencia)
VALUES (:tram_id, :pred_id, :lote_id, :ubic_fecha, :tecn_id, :vigi_id, :ruta_id,
        :retc_id, :loca_id, :arbo_id, :ubic_long, :ubic_lat, :ubic_alt, :ubic_referencia)
"""
                ),
                {**ubicacion, "tram_id": tram_id},
            )
        return int(tram_id)

    async def actualizar_trampa(self, tram_id: int, cambios: dict[str, Any]) -> None:
        """Aplica solo los campos presentes en ``cambios`` (atra_id, esta_id, tecn_id_estado).

        Un cambio de estado fija ``tram_fecha_estado`` y ``tram_tecnico_estado_id``. Siempre se
        actualiza ``tram_fecha_actualizacion`` con la fecha de hoy en la zona del predio (ADR-10).
        ``tram_tecnico_actualizacion_id`` es el técnico de ESTA actualización: ``tecn_id_estado`` o
        nulo si no vino (por ejemplo, solo cambió el atrayente); no se arrastra el anterior.
        """
        await self._con.execute(
            text(
                """
UPDATE sigat.trampa t
   SET atra_id = CASE WHEN CAST(:cambia_atrayente AS boolean)
                      THEN CAST(:atra_id AS integer) ELSE t.atra_id END,
       esta_id = CASE WHEN CAST(:cambia_estado AS boolean)
                      THEN CAST(:esta_id AS integer) ELSE t.esta_id END,
       tram_fecha_estado = CASE WHEN CAST(:cambia_estado AS boolean)
                                THEN h.hoy ELSE t.tram_fecha_estado END,
       tram_tecnico_estado_id = CASE WHEN CAST(:cambia_estado AS boolean)
                                     THEN CAST(:tecnico AS integer) ELSE t.tram_tecnico_estado_id END,
       tram_tecnico_actualizacion_id = CAST(:tecnico AS integer),
       tram_fecha_actualizacion = h.hoy
  FROM (SELECT COALESCE(
                 (SELECT CAST(now() AT TIME ZONE p.pred_zona_horaria AS date)
                    FROM sigat.ubicacion_trampa u
                    JOIN sigat.predio p ON p.pred_id = u.pred_id
                   WHERE u.tram_id = :tram_id AND u.ubic_fecha_fin IS NULL),
                 CURRENT_DATE) AS hoy) h
 WHERE t.tram_id = :tram_id
"""
            ),
            {
                "tram_id": tram_id,
                "cambia_atrayente": "atra_id" in cambios,
                "atra_id": cambios.get("atra_id"),
                "cambia_estado": "esta_id" in cambios,
                "esta_id": cambios.get("esta_id"),
                "tecnico": cambios.get("tecn_id_estado"),
            },
        )

    async def ubicaciones(self, tram_id: int, usua_id: int) -> list[dict[str, Any]]:
        """Historial de ``ubicacion_trampa``, la más reciente primero.

        Solo las ubicaciones en lotes de ``fn_lotes_visibles``: si la trampa estuvo antes en un
        predio ajeno, esa parte no se muestra (toda consulta de lotes se restringe por asignación).
        Las filas heredadas sin lote (``ubic_origen = 'legado'``) tampoco: el contrato
        ``UbicacionTrampa`` exige ``lote_id``.
        """
        filas = await self._con.execute(
            text(
                """
SELECT ubic_id, tram_id, pred_id, lote_id, ubic_fecha, ubic_fecha_fin, tecn_id, vigi_id, ruta_id,
       retc_id, loca_id, arbo_id, ubic_long, ubic_lat, ubic_alt, ubic_referencia, ubic_origen,
       ubic_registrado_en
  FROM sigat.ubicacion_trampa
 WHERE tram_id = :tram_id
   AND lote_id IN (SELECT lote_id FROM sigat.fn_lotes_visibles(:usua))
 ORDER BY ubic_fecha DESC, ubic_id DESC
"""
            ),
            {"tram_id": tram_id, "usua": usua_id},
        )
        return [dict(f) for f in filas.mappings()]

    async def reubicar(self, tram_id: int, nueva: dict[str, Any]) -> int:
        """Cierra la vigente (ubic_fecha_fin = nueva.ubic_fecha) e inserta la nueva."""
        raise NoImplementado("Reubicación")

    # programa / retícula / paquete
    async def programa_vigente(self, pred_id: int, fecha: date) -> dict[str, Any] | None:
        """Vigencia [desde, hasta): ``prog_vigente_desde <= fecha AND (hasta IS NULL OR hasta > fecha)``."""
        raise NoImplementado("Programa vigente")

    async def versiones_programa(self, pred_id: int) -> list[dict[str, Any]]:
        raise NoImplementado("Versiones del programa")

    async def nueva_version_programa(self, pred_id: int, datos: dict[str, Any], creado_por: int) -> int:
        """Cierra la vigente y crea la siguiente + programa_umbral + programa_criterio_bpa."""
        raise NoImplementado("Nueva versión del programa")

    async def reticula(self, pred_id: int) -> dict[str, Any] | None:
        raise NoImplementado("Retícula")

    async def insertar_reticula(
        self, pred_id: int, resolucion_m: int, corte: date | None, celdas: list[dict[str, Any]]
    ) -> int:
        """La retícula es inmutable (fn_reticula_inmutable): una nueva resolución = nueva retícula."""
        raise NoImplementado("Alta de retícula")

    async def paquete_vigente(self, pred_id: int) -> dict[str, Any] | None:
        raise NoImplementado("Paquete vigente")

    async def registrar_paquete(self, pred_id: int, prog_id: int, hash_hex: str) -> UUID:
        raise NoImplementado("Registrar paquete")

    async def invalidar_paquetes(self, pred_id: int, motivo: str) -> None:
        raise NoImplementado("Invalidar paquetes")

    async def contar_lotes_sobre_umbral(self, usua_id: int) -> int:
        """Cuenta lotes visibles del agronomo cuyo MTD supera el umbral fitosanitario."""
        sql = """
        SELECT count(*)::int
          FROM sigat.v_lote_resumen_app vlra
          JOIN sigat.fn_lotes_visibles(:u) lv ON lv.lote_id = vlra.lote_id
        WHERE vlra.contraste = 'igual_o_superior_umbral'
          OR vlra.escenario IN ('Supresión', 'Área infestada')
        """
        resultado = await self._con.scalar(text(sql), {"u": usua_id})
        return int(resultado or 0)
