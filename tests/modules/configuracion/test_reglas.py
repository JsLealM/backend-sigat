"""Reglas del módulo configuracion: pendientes de implementar (cada una cuenta para RNF-017)."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from sigat_api.compartido.errores import Conflicto
from sigat_api.compartido.tipos import Actor, Cliente, RolCodigo
from sigat_api.modules.configuracion import esquemas as e
from sigat_api.modules.configuracion.servicio import ServicioTrampas

PENDIENTE = pytest.mark.skip(reason="Por implementar")


class _RepoCodigoExistente:
    """Lote visible, tipo Jackson y el código ya registrado en el catálogo."""

    async def lote_visible(self, usua_id: int, lote_id: int) -> bool:
        return True

    async def predio_del_lote(self, lote_id: int) -> int:
        return 1

    async def lote_activo_en(self, lote_id: int, fecha: date) -> bool:
        return True

    async def tipo_trampa(self, tipt_id: int) -> dict[str, Any]:
        return {"tipt_id": 1, "tipt_descripcion": "Jackson", "tipt_paridad": "impar"}

    async def existe_codigo_trampa(self, tram_codigo: str) -> bool:
        return True


@pytest.mark.regla
async def test_configuracion_01() -> None:
    """código de trampa duplicado da 409 'Duplicidad de código de trampa'."""
    actor = Actor(usua_id=2, rol=RolCodigo.AGRONOMO_SUPERVISOR, disp_id=None, cliente=Cliente.WEB)
    nueva = e.NuevaTrampa(
        tram_codigo="15001-602-001",
        tipt_id=1,
        atra_id=1,
        ubicacion=e.NuevaUbicacion(
            lote_id=1,
            ubic_fecha=date(2026, 11, 13),
            vigi_id=1,
            tecn_id=1,
            ubic_long=Decimal("-73.35950"),
            ubic_lat=Decimal("5.53050"),
        ),
    )

    with pytest.raises(Conflicto) as error:
        await ServicioTrampas(_RepoCodigoExistente(), None).crear(actor, nueva)  # type: ignore[arg-type]

    assert error.value.estado_http == 409
    assert error.value.codigo == "CODIGO_TRAMPA_DUPLICADO"
    assert "Duplicidad de código de trampa" in error.value.detalle


@pytest.mark.regla
@PENDIENTE
def test_configuracion_02() -> None:
    """nueva versión del programa no altera periodos ya calculados (ADR-05)."""


@pytest.mark.regla
@PENDIENTE
def test_configuracion_03() -> None:
    """retícula menor o igual a la distancia mínima se rechaza (§5.3)."""


@pytest.mark.regla
@PENDIENTE
def test_configuracion_04() -> None:
    """búsqueda de trampa inexistente responde en_catalogo=false (no 404)."""


@pytest.mark.regla
@PENDIENTE
def test_configuracion_05() -> None:
    """trampa fuera del lote ADVIERTE y no bloquea (RF-012)."""


@pytest.mark.regla
@PENDIENTE
def test_configuracion_06() -> None:
    """paquete de campo responde 304 con If-None-Match vigente."""
