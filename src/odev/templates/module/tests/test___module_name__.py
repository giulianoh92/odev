from odoo.tests.common import TransactionCase


class Test__module_name__(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.record = cls.env["__module_name__"].create({
            "name": "Registro de prueba",
            "amount": 100.0,
        })

    def test_create(self):
        """Verifica que se cree correctamente un registro."""
        self.assertEqual(self.record.name, "Registro de prueba")
        self.assertEqual(self.record.amount, 100.0)
        self.assertTrue(self.record.active)

    def test_display_name(self):
        """Verifica que el nombre para mostrar sea correcto."""
        self.assertEqual(self.record.display_name, "Registro de prueba")
