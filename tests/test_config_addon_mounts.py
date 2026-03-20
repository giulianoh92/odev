"""Tests para la funcion construir_addon_mounts de odev.core.config.

Valida la generacion correcta de mounts Docker a partir de listas
de rutas de addons, incluyendo rutas relativas, absolutas y listas vacias.
"""

from pathlib import Path

from odev.core.config import construir_addon_mounts


class TestConstruirAddonMounts:
    """Tests para construir_addon_mounts()."""

    def test_single_relative(self) -> None:
        """Una ruta relativa genera un mount en /mnt/extra-addons."""
        mounts = construir_addon_mounts(["./addons"], Path("/project"))

        assert len(mounts) == 1
        assert mounts[0]["container_path"] == "/mnt/extra-addons"
        assert mounts[0]["host_path"] == "./addons"

    def test_multiple_absolute(self) -> None:
        """Multiples rutas absolutas generan mounts con sufijo numerico."""
        mounts = construir_addon_mounts(
            ["/home/user/repo", "/home/user/repo/oca-web"],
            Path("/config"),
        )

        assert len(mounts) == 2
        assert mounts[0]["container_path"] == "/mnt/extra-addons"
        assert mounts[1]["container_path"] == "/mnt/extra-addons-1"

    def test_empty_list(self) -> None:
        """Lista vacia retorna lista vacia."""
        mounts = construir_addon_mounts([], Path("/project"))

        assert mounts == []

    def test_nombre_se_deriva_del_path(self) -> None:
        """El campo 'nombre' se deriva del ultimo componente del path."""
        mounts = construir_addon_mounts(["/home/user/my-addons"], Path("/config"))

        assert mounts[0]["nombre"] == "my-addons"

    def test_nombre_dot_path(self) -> None:
        """Si el path es '.', Path('.').name es '' (string vacio)."""
        mounts = construir_addon_mounts(["."], Path("/config"))

        # Path(".").name returns "" — el campo nombre queda vacio
        assert mounts[0]["nombre"] == ""

    def test_tres_mounts_numeracion_secuencial(self) -> None:
        """Tres mounts generan /mnt/extra-addons, -1 y -2."""
        mounts = construir_addon_mounts(
            ["./addons", "./enterprise", "./oca-web"],
            Path("/project"),
        )

        assert len(mounts) == 3
        assert mounts[0]["container_path"] == "/mnt/extra-addons"
        assert mounts[1]["container_path"] == "/mnt/extra-addons-1"
        assert mounts[2]["container_path"] == "/mnt/extra-addons-2"

    def test_host_path_relativa_se_conserva(self) -> None:
        """Rutas relativas se conservan tal cual (para docker-compose)."""
        mounts = construir_addon_mounts(["../otro-repo/addons"], Path("/project"))

        assert mounts[0]["host_path"] == "../otro-repo/addons"

    def test_host_path_absoluta_se_conserva(self) -> None:
        """Rutas absolutas se conservan como string del Path absoluto."""
        mounts = construir_addon_mounts(["/abs/path/addons"], Path("/project"))

        assert mounts[0]["host_path"] == "/abs/path/addons"
