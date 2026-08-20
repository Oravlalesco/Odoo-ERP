from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class WmsProductLogistics(models.Model):
    """Perfil logístico WMS — companion 1:1 de product.template.

    PLM-002: Identidad core y link one-to-one.
    PLM-003A: Roles UOM operacionales (pick, case, pallet).
    PLM-003B: Configuración Ti-Hi y cantidades derivadas.

    Cada product.template puede tener como máximo un perfil
    logístico WMS.  El perfil no se crea automáticamente;
    se asigna bajo demanda por un usuario autorizado.

    Campos funcionales (PLM-002):
        product_tmpl_id  → producto Odoo (required, cascade)
        company_id       → derived de product_tmpl_id, puede ser False
        active           → derived de product_tmpl_id

    Campos funcionales (PLM-003A):
        pick_uom_id      → UOM de pick (base o packaging)
        case_uom_id      → UOM de case (sólo packaging)
        pallet_uom_id    → UOM de pallet (sólo packaging)

    Campos funcionales (PLM-003B):
        cases_per_layer     → Cajas por capa (Ti, WMS-owned)
        layers_per_pallet   → Capas por pallet (Hi, WMS-owned)
        base_qty_per_case   → Cantidad base por caja (derived Odoo UOM)
        cases_per_pallet    → Cajas por pallet (derived Odoo UOM)
        base_qty_per_pallet → Cantidad base por pallet (derived Odoo UOM)

    Campos funcionales (PLM-004):
        abc_class           → Selección ABC (A, B, C)
        velocity_class      → Selección velocidad (FAST, MEDIUM, SLOW, DEAD)
        temperature_class   → Selección temperatura (AMBIENT, CHILLED, FROZEN, ULTRA_FROZEN)
        hazmat_class        → Selección hazmat (NONE, CLASS_1..CLASS_9)
        stackable           → Boolean apilable
        max_stack           → Integer niveles máximos de apilado (>= 0)
        fragile             → Boolean producto frágil

    Campos funcionales (PLM-005A):
        min_shelf_life_receipt_days  → Días mínimos vida útil al recibir (>= 0)
        min_shelf_life_shipping_days → Días mínimos vida útil al despachar (>= 0)

    Campos funcionales (PLM-005B):
        allowed_hu_type_ids → Tipos HU permitidos (Many2many stock.package.type)
        default_hu_type_id  → Tipo HU por defecto (Many2one stock.package.type, ondelete='restrict')

    Campos funcionales (PLM-006A):
        requires_quality_inspection → Boolean (requerimiento maestro de inspección)
        quality_inspection_type     → Selection (VISUAL, DIMENSIONAL, SAMPLING)
        quality_sampling_rate       → Float (porcentaje de muestreo, 0..100)

    Lifecycle:
        - Crear producto no crea perfil
        - Archivar producto → perfil queda active=False
        - Reactivar producto → perfil vuelve a active=True
        - Eliminar producto → perfil eliminado (cascade)
        - Eliminar perfil → producto permanece
    """

    _name = "wms.product.logistics"
    _description = "Perfil logístico WMS de producto"
    _order = "product_tmpl_id, id"
    _rec_name = "product_tmpl_id"

    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Producto",
        required=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        related="product_tmpl_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    active = fields.Boolean(
        string="Activo",
        related="product_tmpl_id.active",
        store=True,
        readonly=True,
    )

    # ------------------------------------------------------------------
    # PLM-003A: Operational UOM Roles
    # ------------------------------------------------------------------

    pick_uom_id = fields.Many2one(
        "uom.uom",
        string="UOM de Pick",
        ondelete="restrict",
        help="UOM operacional de pick. "
        "Puede ser la UOM base del producto o un packaging adicional.",
    )
    case_uom_id = fields.Many2one(
        "uom.uom",
        string="UOM de Case",
        ondelete="restrict",
        help="UOM operacional de case. "
        "Debe ser un packaging adicional del producto (uom_ids).",
    )
    pallet_uom_id = fields.Many2one(
        "uom.uom",
        string="UOM de Pallet",
        ondelete="restrict",
        help="UOM operacional de pallet. "
        "Debe ser un packaging adicional del producto (uom_ids).",
    )

    # ------------------------------------------------------------------
    # PLM-003B: Ti-Hi Configuration & Derived Quantities
    # ------------------------------------------------------------------

    cases_per_layer = fields.Integer(
        string="Cajas por capa (Ti)",
        help="Número de cajas por capa en el pallet (Ti). "
        "0 indica no configurado.",
    )
    layers_per_pallet = fields.Integer(
        string="Capas por pallet (Hi)",
        help="Número de capas por pallet (Hi). "
        "0 indica no configurado.",
    )

    base_qty_per_case = fields.Float(
        string="Cantidad base por caja",
        compute="_compute_derived_quantities",
        readonly=True,
        store=False,
        help="Cantidad de unidades base por caja, derivada de la UOM de case.",
    )
    cases_per_pallet = fields.Float(
        string="Cajas por pallet",
        compute="_compute_derived_quantities",
        readonly=True,
        store=False,
        help="Cantidad de cajas por pallet, derivada de la UOM de pallet y case.",
    )
    base_qty_per_pallet = fields.Float(
        string="Cantidad base por pallet",
        compute="_compute_derived_quantities",
        readonly=True,
        store=False,
        help="Cantidad de unidades base por pallet, derivada de la UOM de pallet.",
    )

    # ------------------------------------------------------------------
    # PLM-004: Operational Classifications & Handling Attributes
    # ------------------------------------------------------------------

    abc_class = fields.Selection(
        selection=[
            ("A", "Clase A"),
            ("B", "Clase B"),
            ("C", "Clase C"),
        ],
        string="Clase ABC",
        help="Clasificación ABC por valor o rotación.",
    )
    velocity_class = fields.Selection(
        selection=[
            ("FAST", "Rápido (Fast)"),
            ("MEDIUM", "Medio (Medium)"),
            ("SLOW", "Lento (Slow)"),
            ("DEAD", "Sin movimiento (Dead)"),
        ],
        string="Clase de Velocidad",
        help="Clasificación por velocidad de movimiento.",
    )
    temperature_class = fields.Selection(
        selection=[
            ("AMBIENT", "Ambiente (Ambient)"),
            ("CHILLED", "Refrigerado (Chilled)"),
            ("FROZEN", "Congelado (Frozen)"),
            ("ULTRA_FROZEN", "Ultra-congelado (Ultra Frozen)"),
        ],
        string="Clase de Temperatura",
        help="Requisito de control de temperatura.",
    )
    hazmat_class = fields.Selection(
        selection=[
            ("NONE", "No peligroso (None)"),
            ("CLASS_1", "Clase 1 - Explosivos"),
            ("CLASS_2", "Clase 2 - Gases"),
            ("CLASS_3", "Clase 3 - Líquidos inflamables"),
            ("CLASS_4", "Clase 4 - Sólidos inflamables"),
            ("CLASS_5", "Clase 5 - Oxidantes"),
            ("CLASS_6", "Clase 6 - Tóxicos"),
            ("CLASS_7", "Clase 7 - Radiactivos"),
            ("CLASS_8", "Clase 8 - Corrosivos"),
            ("CLASS_9", "Clase 9 - Misceláneos"),
        ],
        string="Clase Hazmat",
        help="Clasificación de material peligroso.",
    )

    stackable = fields.Boolean(
        string="Apilable",
        help="Indica si el producto o su packaging es físicamente apilable.",
    )
    max_stack = fields.Integer(
        string="Máximo de apilado",
        help="Número máximo de niveles de apilado permitidos.",
    )
    fragile = fields.Boolean(
        string="Frágil",
        help="Indica si el producto requiere manipulación especial como frágil.",
    )

    # ------------------------------------------------------------------
    # PLM-005A: Shelf-Life Policy Master
    # ------------------------------------------------------------------

    min_shelf_life_receipt_days = fields.Integer(
        string="Vida útil mínima al recibir (días)",
        help="Días mínimos de vida útil restante requeridos al recibir en recepción. "
        "0 indica sin requisito.",
    )
    min_shelf_life_shipping_days = fields.Integer(
        string="Vida útil mínima al despachar (días)",
        help="Días mínimos de vida útil restante requeridos al despachar. "
        "0 indica sin requisito.",
    )

    # ------------------------------------------------------------------
    # PLM-005B: HU Type Restrictions
    # ------------------------------------------------------------------

    allowed_hu_type_ids = fields.Many2many(
        "stock.package.type",
        string="Tipos HU permitidos",
        help="Tipos de unidad de manejo (HU) permitidos para este producto. "
        "Si está vacío, no hay restricción de tipo.",
    )
    default_hu_type_id = fields.Many2one(
        "stock.package.type",
        string="Tipo HU por defecto",
        ondelete="restrict",
        help="Tipo de unidad de manejo (HU) preferido por defecto al recibir o empacar. "
        "Si se especifican tipos permitidos, debe pertenecer a dicha lista.",
    )

    # ------------------------------------------------------------------
    # PLM-006A: Quality Inspection Policy Master
    # ------------------------------------------------------------------

    requires_quality_inspection = fields.Boolean(
        string="Requiere inspección de calidad",
        help="Indica si el producto declara un requerimiento maestro de inspección al recibir. "
        "False no impide inspecciones determinadas dinámicamente por reglas de recepción.",
    )
    quality_inspection_type = fields.Selection(
        selection=[
            ("VISUAL", "Visual"),
            ("DIMENSIONAL", "Dimensional"),
            ("SAMPLING", "Muestreo"),
        ],
        string="Tipo de inspección de calidad",
        help="Tipo de inspección preferido o configurado para el producto.",
    )
    quality_sampling_rate = fields.Float(
        string="Porcentaje de muestreo de calidad (%)",
        help="Porcentaje de muestreo preferido para inspección (0 a 100). "
        "0 indica sin porcentaje maestro predefinido.",
    )

    @api.depends(
        "product_tmpl_id.uom_id",
        "product_tmpl_id.uom_id.factor",
        "case_uom_id",
        "case_uom_id.factor",
        "pallet_uom_id",
        "pallet_uom_id.factor",
    )
    def _compute_derived_quantities(self):
        for profile in self:
            product = profile.product_tmpl_id
            base_uom = product.uom_id if product else False
            case_uom = profile.case_uom_id
            pallet_uom = profile.pallet_uom_id

            # base_qty_per_case
            if case_uom and base_uom:
                profile.base_qty_per_case = case_uom._compute_quantity(
                    1.0, base_uom, round=False,
                )
            else:
                profile.base_qty_per_case = 0.0

            # cases_per_pallet
            if pallet_uom and case_uom:
                profile.cases_per_pallet = pallet_uom._compute_quantity(
                    1.0, case_uom, round=False,
                )
            else:
                profile.cases_per_pallet = 0.0

            # base_qty_per_pallet
            if pallet_uom and base_uom:
                profile.base_qty_per_pallet = pallet_uom._compute_quantity(
                    1.0, base_uom, round=False,
                )
            else:
                profile.base_qty_per_pallet = 0.0

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    _unique_product = models.Constraint(
        "UNIQUE(product_tmpl_id)",
        "Sólo puede existir un perfil logístico WMS por producto.",
    )

    _check_max_stack = models.Constraint(
        "CHECK(max_stack >= 0)",
        "El máximo de apilado no puede ser negativo.",
    )

    _check_min_shelf_life_receipt = models.Constraint(
        "CHECK(min_shelf_life_receipt_days >= 0)",
        "La vida útil mínima al recibir no puede ser negativa.",
    )

    _check_min_shelf_life_shipping = models.Constraint(
        "CHECK(min_shelf_life_shipping_days >= 0)",
        "La vida útil mínima al despachar no puede ser negativa.",
    )

    _check_quality_sampling_rate = models.Constraint(
        "CHECK(quality_sampling_rate >= 0 AND quality_sampling_rate <= 100)",
        "El porcentaje de muestreo de calidad debe estar entre 0 y 100.",
    )

    @api.constrains(
        "product_tmpl_id",
        "pick_uom_id",
        "case_uom_id",
        "pallet_uom_id",
    )
    def _check_operational_uom_roles(self):
        """Validar que las UOM operacionales pertenecen al producto.

        - pick_uom_id: puede ser product.uom_id (base) O product.uom_ids
        - case_uom_id: sólo product.uom_ids (packaging adicional)
        - pallet_uom_id: sólo product.uom_ids (packaging adicional)
        """
        for profile in self:
            product = profile.product_tmpl_id
            base_uom = product.uom_id
            packaging_uoms = product.uom_ids
            all_valid = base_uom | packaging_uoms

            if profile.pick_uom_id and profile.pick_uom_id not in all_valid:
                raise ValidationError(_(
                    "La UOM de pick '%(uom)s' no pertenece al producto "
                    "'%(product)s'. Debe ser la UOM base o un packaging "
                    "adicional.",
                    uom=profile.pick_uom_id.name,
                    product=product.display_name,
                ))

            if profile.case_uom_id:
                if profile.case_uom_id not in packaging_uoms:
                    raise ValidationError(_(
                        "La UOM de case '%(uom)s' no es un packaging "
                        "adicional del producto '%(product)s'.",
                        uom=profile.case_uom_id.name,
                        product=product.display_name,
                    ))

            if profile.pallet_uom_id:
                if profile.pallet_uom_id not in packaging_uoms:
                    raise ValidationError(_(
                        "La UOM de pallet '%(uom)s' no es un packaging "
                        "adicional del producto '%(product)s'.",
                        uom=profile.pallet_uom_id.name,
                        product=product.display_name,
                    ))

    @api.constrains(
        "cases_per_layer",
        "layers_per_pallet",
        "case_uom_id",
        "pallet_uom_id",
        "product_tmpl_id",
    )
    def _check_tihi_configuration(self):
        """Validar coherencia de la configuración Ti-Hi con las UOM de Odoo.

        - Ti y Hi deben configurarse juntos (ambos > 0) o ninguno (ambos == 0).
        - Valores negativos están prohibidos.
        - Si Ti/Hi están configurados, deben definirse case_uom_id y pallet_uom_id.
        - Ti × Hi debe reconciliar con cases_per_pallet derivado de Odoo UOM.
        """
        for profile in self:
            ti = profile.cases_per_layer
            hi = profile.layers_per_pallet

            # Valores negativos
            if ti < 0 or hi < 0:
                raise ValidationError(_(
                    "Los valores de Ti (cajas por capa) y Hi (capas por pallet) "
                    "no pueden ser negativos.",
                ))

            # No configurado (0, 0) es válido
            if ti == 0 and hi == 0:
                continue

            # Configuración parcial no permitida
            if ti == 0 or hi == 0:
                raise ValidationError(_(
                    "La configuración Ti-Hi es incompleta. Ti y Hi deben "
                    "configurarse juntos o permanecer ambos en 0.",
                ))

            # Ti > 0 y Hi > 0 requiere case_uom_id y pallet_uom_id
            if not profile.case_uom_id or not profile.pallet_uom_id:
                raise ValidationError(_(
                    "Para configurar Ti-Hi es obligatorio definir tanto la "
                    "UOM de case como la UOM de pallet.",
                ))

            # Reconciliación Ti × Hi == cases_per_pallet
            expected_cases = float(ti * hi)
            derived_cases = profile.pallet_uom_id._compute_quantity(
                1.0, profile.case_uom_id, round=False,
            )
            if float_compare(expected_cases, derived_cases, precision_digits=4) != 0:
                raise ValidationError(_(
                    "Inconsistencia en Ti-Hi para '%(product)s': "
                    "Ti (%(ti)d) × Hi (%(hi)d) = %(expected)d cajas por pallet, "
                    "pero la UOM de pallet '%(pallet)s' equivale a %(derived).2f "
                    "cajas de '%(case)s'.",
                    product=profile.product_tmpl_id.display_name,
                    ti=ti,
                    hi=hi,
                    expected=int(expected_cases),
                    pallet=profile.pallet_uom_id.name,
                    derived=derived_cases,
                    case=profile.case_uom_id.name,
                ))

    @api.constrains("stackable", "max_stack")
    def _check_stackability(self):
        """Validar coherencia entre stackable y max_stack.

        - stackable = False  →  max_stack DEBE ser 0
        - stackable = True   →  max_stack DEBE ser >= 2
        """
        for profile in self:
            if not profile.stackable and profile.max_stack != 0:
                raise ValidationError(_(
                    "Si el producto no es apilable, el máximo de apilado debe ser 0.",
                ))
            if profile.stackable and profile.max_stack < 2:
                raise ValidationError(_(
                    "Si el producto es apilable, el máximo de apilado debe ser al menos 2 niveles.",
                ))

    @api.constrains(
        "product_tmpl_id",
        "allowed_hu_type_ids",
        "default_hu_type_id",
    )
    def _check_hu_type_restrictions(self):
        """Validar restricciones de tipos HU y coherencia multi-compañía.

        1. Compatibilidad multi-company de allowed_hu_type_ids:
           - Si el producto tiene compañía: tipos permitidos deben ser globales o de la misma compañía.
           - Si el producto es global (company_id=False): tipos permitidos deben ser globales (company_id=False).
        2. Compatibilidad multi-company de default_hu_type_id:
           - Si el producto tiene compañía: tipo por defecto debe ser global o de la misma compañía.
           - Si el producto es global: tipo por defecto debe ser global.
        3. Pertenencia de default_hu_type_id:
           - Si allowed_hu_type_ids no está vacío: default_hu_type_id DEBE pertenecer a allowed_hu_type_ids.
        """
        for profile in self:
            product = profile.product_tmpl_id
            product_company = product.company_id
            allowed = profile.allowed_hu_type_ids
            default = profile.default_hu_type_id

            # 1. Compatibilidad multi-company de tipos permitidos
            for hu_type in allowed:
                if product_company:
                    if hu_type.company_id and hu_type.company_id != product_company:
                        raise ValidationError(_(
                            "El tipo HU '%(hu_type)s' pertenece a la compañía '%(type_company)s', "
                            "incompatible con el producto '%(product)s' (compañía '%(prod_company)s').",
                            hu_type=hu_type.display_name,
                            type_company=hu_type.company_id.name,
                            product=product.display_name,
                            prod_company=product_company.name,
                        ))
                else:
                    if hu_type.company_id:
                        raise ValidationError(_(
                            "El tipo HU '%(hu_type)s' pertenece a la compañía '%(type_company)s', "
                            "pero el producto '%(product)s' es global y solo admite tipos HU globales.",
                            hu_type=hu_type.display_name,
                            type_company=hu_type.company_id.name,
                            product=product.display_name,
                        ))

            # 2. Compatibilidad multi-company del tipo por defecto
            if default:
                if product_company:
                    if default.company_id and default.company_id != product_company:
                        raise ValidationError(_(
                            "El tipo HU por defecto '%(hu_type)s' pertenece a la compañía '%(type_company)s', "
                            "incompatible con el producto '%(product)s' (compañía '%(prod_company)s').",
                            hu_type=default.display_name,
                            type_company=default.company_id.name,
                            product=product.display_name,
                            prod_company=product_company.name,
                        ))
                else:
                    if default.company_id:
                        raise ValidationError(_(
                            "El tipo HU por defecto '%(hu_type)s' pertenece a la compañía '%(type_company)s', "
                            "pero el producto '%(product)s' es global y solo admite tipos HU globales.",
                            hu_type=default.display_name,
                            type_company=default.company_id.name,
                            product=product.display_name,
                        ))

            # 3. Pertenencia del default a los tipos permitidos cuando la lista no está vacía
            if allowed and default:
                if default not in allowed:
                    raise ValidationError(_(
                        "El tipo HU por defecto '%(default)s' no pertenece a la lista de tipos HU permitidos "
                        "para el producto '%(product)s'.",
                        default=default.display_name,
                        product=product.display_name,
                    ))
