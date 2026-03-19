from odoo.tests.common import TransactionCase


class Test__module_name__(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.record = cls.env["__module_name__"].create({
            "name": "Test Record",
            "amount": 100.0,
        })

    def test_create(self):
        self.assertEqual(self.record.name, "Test Record")
        self.assertEqual(self.record.amount, 100.0)
        self.assertTrue(self.record.active)

    def test_display_name(self):
        self.assertEqual(self.record.display_name, "Test Record")
