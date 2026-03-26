"""Tests para odev.commands.reconfigure — comando de regeneracion de configuracion."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from odev.core.project import ProjectConfig
from odev.core.regen import (
    RegenResult,
    necesita_regeneracion,
    regenerar_configuracion,
)
from odev.core.resolver import ModoProyecto, ProjectContext


def _crear_contexto(directorio: Path) -> ProjectContext:
    """Helper: crea un ProjectContext apuntando al directorio dado."""
    config = ProjectConfig(directorio)
    return ProjectContext(
        nombre="test-reconfig",
        modo=ModoProyecto.INLINE,
        directorio_config=directorio,
        directorio_trabajo=directorio,
        config=config,
    )


class TestDryRunNoFileChanges:
    """Verifica que --dry-run no modifica archivos en disco."""

    def test_dry_run_no_file_changes(self, directorio_proyecto: Path) -> None:
        """--dry-run (via necesita_regeneracion) no modifica ningun archivo."""
        compose_before = (directorio_proyecto / "docker-compose.yml").read_text()
        env_before = (directorio_proyecto / ".env").read_text()

        ctx = _crear_contexto(directorio_proyecto)

        # necesita_regeneracion es lo que dry_run llama — no debe modificar nada
        necesita_regeneracion(ctx)

        compose_after = (directorio_proyecto / "docker-compose.yml").read_text()
        env_after = (directorio_proyecto / ".env").read_text()

        assert compose_before == compose_after
        assert env_before == env_after


class TestReconfigureUpdatesCompose:
    """Verifica que docker-compose.yml se regenera correctamente."""

    def test_reconfigure_updates_compose(self, directorio_proyecto: Path) -> None:
        """regenerar_configuracion regenera docker-compose.yml."""
        ctx = _crear_contexto(directorio_proyecto)
        resultado = regenerar_configuracion(ctx)

        # docker-compose.yml deberia haber sido regenerado (el contenido original
        # era un stub minimo, el template produce algo diferente)
        compose = directorio_proyecto / "docker-compose.yml"
        assert compose.exists()
        contenido = compose.read_text()
        # El template real genera contenido con 'services:'
        assert "services:" in contenido
        # Deberia aparecer en la lista de regenerados
        assert any(p.name == "docker-compose.yml" for p in resultado.archivos_regenerados)


class TestReconfigurePreservesEnv:
    """Verifica que .env no se toca por defecto."""

    def test_reconfigure_preserves_env(self, directorio_proyecto: Path) -> None:
        """.env no se modifica cuando include_env=False (defecto)."""
        env_antes = (directorio_proyecto / ".env").read_text()

        ctx = _crear_contexto(directorio_proyecto)
        regenerar_configuracion(ctx, include_env=False)

        env_despues = (directorio_proyecto / ".env").read_text()
        assert env_antes == env_despues


class TestNecesitaRegeneracion:
    """Tests para la funcion necesita_regeneracion."""

    def test_retorna_true_cuando_yaml_mas_nuevo(self, directorio_proyecto: Path) -> None:
        """Retorna True si .odev.yaml es mas nuevo que docker-compose.yml."""
        import os
        import time

        ctx = _crear_contexto(directorio_proyecto)

        # Asegurar que compose tiene un mtime anterior
        compose = directorio_proyecto / "docker-compose.yml"
        yaml_file = directorio_proyecto / ".odev.yaml"

        # Tocar .odev.yaml para que sea mas nuevo
        time.sleep(0.05)
        yaml_file.write_text(yaml_file.read_text())

        assert necesita_regeneracion(ctx) is True

    def test_retorna_false_cuando_actualizado(self, directorio_proyecto: Path) -> None:
        """Retorna False si los archivos generados son mas nuevos que .odev.yaml."""
        import time

        ctx = _crear_contexto(directorio_proyecto)

        # Regenerar para actualizar timestamps
        regenerar_configuracion(ctx)

        # Ahora los archivos generados son mas nuevos
        assert necesita_regeneracion(ctx) is False

    def test_retorna_true_cuando_falta_compose(self, directorio_proyecto: Path) -> None:
        """Retorna True si docker-compose.yml no existe."""
        ctx = _crear_contexto(directorio_proyecto)

        compose = directorio_proyecto / "docker-compose.yml"
        compose.unlink()

        assert necesita_regeneracion(ctx) is True

    def test_retorna_false_sin_odev_yaml(self, tmp_path: Path) -> None:
        """Retorna False si .odev.yaml no existe."""
        # Crear un contexto con directorio sin .odev.yaml
        ctx = ProjectContext(
            nombre="test",
            modo=ModoProyecto.INLINE,
            directorio_config=tmp_path,
            directorio_trabajo=tmp_path,
            config=None,
        )

        assert necesita_regeneracion(ctx) is False


class TestRegenResult:
    """Tests para la estructura RegenResult."""

    def test_inicializacion_vacia(self) -> None:
        """RegenResult se inicializa con listas vacias."""
        resultado = RegenResult()
        assert resultado.archivos_regenerados == []
        assert resultado.archivos_sin_cambios == []
        assert resultado.advertencias == []
