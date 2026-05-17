"""Tests de concurrencia para allocate_ports — asignacion atomica multi-proceso.

Verifica REQ-PA-1 (Scenario 2) y NF-2: 5 wizards concurrentes producen
conjuntos de puertos disjuntos. Usa threading para simular concurrencia
intra-proceso y verifica que el mecanismo de flock garantice aislamiento.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from odev.core.ports import CONJUNTOS_PUERTOS, allocate_ports
from odev.core.registry import Registry


@pytest.fixture
def registry_concurrencia(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Registry:
    """Fixture de registro aislado para tests de concurrencia.

    Redirige todas las rutas globales a tmp_path para evitar contaminar
    el registro real del sistema.
    """
    import odev.core.registry as reg_mod

    monkeypatch.setattr(reg_mod, "ODEV_HOME", tmp_path)
    monkeypatch.setattr(reg_mod, "REGISTRY_PATH", tmp_path / "registry.yaml")
    monkeypatch.setattr(reg_mod, "PROJECTS_DIR", tmp_path / "projects")
    (tmp_path / "projects").mkdir()
    return Registry()


class TestThreadingAllocatePorts:
    """Verifica que allocate_ports no genere colisiones con threads concurrentes."""

    def test_threading_allocate_ports_no_collision(
        self, registry_concurrencia: Registry
    ) -> None:
        """10 threads concurrentes obtienen conjuntos de puertos completamente disjuntos.

        NF-2: 5+ invocaciones simultaneas de allocate_ports no producen
        conjuntos solapados.
        """
        n_threads = 10
        resultados: list[dict[str, int]] = []
        errores: list[Exception] = []
        lock = threading.Lock()

        def worker(idx: int) -> None:
            """Cada thread reclama un conjunto de puertos."""
            try:
                ports = allocate_ports(f"proyecto-{idx}", registry_concurrencia)
                with lock:
                    resultados.append(ports)
            except Exception as e:
                with lock:
                    errores.append(e)

        # Patch al nivel del test (thread-safe) — no por-thread
        with patch("odev.core.ports.puerto_disponible", return_value=True):
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert not errores, f"Errores en threads: {errores}"
        assert len(resultados) == n_threads

        # Verificar que los conjuntos de WEB_PORT son todos distintos
        web_ports = [r["WEB_PORT"] for r in resultados]
        assert len(set(web_ports)) == n_threads, (
            f"Colision detectada en WEB_PORT: {sorted(web_ports)}"
        )

        # Verificar que ningun puerto aparece en mas de un resultado
        todos_los_puertos: list[int] = []
        for resultado in resultados:
            todos_los_puertos.extend(resultado.values())
        assert len(todos_los_puertos) == len(set(todos_los_puertos)), (
            "Se detectaron puertos duplicados entre conjuntos concurrentes"
        )

    def test_5_concurrent_allocations_produce_distinct_sets(
        self, registry_concurrencia: Registry
    ) -> None:
        """5 allocaciones concurrentes producen 5 conjuntos totalmente disjuntos.

        REQ-PA-1 Scenario 2 — version thread-based.
        """
        n = 5
        resultados: list[dict[str, int]] = []
        barrier = threading.Barrier(n)  # Sincroniza arranque simultaneo

        def worker(idx: int) -> None:
            barrier.wait()  # Todos arrancan a la vez
            ports = allocate_ports(f"wizard-{idx}", registry_concurrencia)
            resultados.append(ports)

        # Patch al nivel del test (thread-safe) — no por-thread
        with patch("odev.core.ports.puerto_disponible", return_value=True):
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(resultados) == n

        # Todos los offsets son distintos
        offsets = [r["WEB_PORT"] - CONJUNTOS_PUERTOS["WEB_PORT"] for r in resultados]
        assert len(set(offsets)) == n, f"Offsets duplicados: {sorted(offsets)}"
