from odoo import api, fields, models


class __module_name__(models.Model):
    _name = "__module_name__"
    _description = "__module_name__"

    name = fields.Char(string="Name", required=True)
    description = fields.Text(string="Description")
    active = fields.Boolean(string="Active", default=True)
    sequence = fields.Integer(string="Sequence", default=10)
    partner_id = fields.Many2one("res.partner", string="Partner")
    amount = fields.Float(string="Amount", digits=(16, 2))

    @api.depends("name")
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.name or ""
