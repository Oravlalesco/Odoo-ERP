from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestOperationalClassifications(TransactionCase):
    """PLM-004: Validar clasificaciones operacionales y atributos de manejo.

    Cubre: contrato de campos (Selection, Boolean, Integer), catálogos
    Selection cerrados, perfiles no clasificados válidos, persistencia
    de clasificaciones, hazmat NONE vs False y limpieza, atributos de
    manejo válidos e independencia de fragile, rechazo de max_stack
    negativo por DB CHECK, y coherencia stackable ↔ max_stack.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.WPL = cls.env["wms.product.logistics"]
        cls.PT = cls.env["product.template"]
        cls.company = cls.env.company

        cls.product_1 = cls.PT.create({
            "name": "Classifications Test Product 1",
            "company_id": cls.company.id,
        })
        cls.product_2 = cls.PT.create({
            "name": "Classifications Test Product 2",
            "company_id": cls.company.id,
        })
        cls.product_3 = cls.PT.create({
            "name": "Classifications Test Product 3",
            "company_id": cls.company.id,
        })

    # ------------------------------------------------------------------
    # TEST-PLM-031: Contrato de campos
    # ------------------------------------------------------------------

    def test_plm_031_field_contract(self):
        """PLM-004-031: tipos, optionalidad, sin index y sin default en selections."""
        WPL = self.env["wms.product.logistics"]

        # Selection fields
        for field_name in ("abc_class", "velocity_class", "temperature_class", "hazmat_class"):
            f = WPL._fields[field_name]
            self.assertEqual(f.type, "selection", f"{field_name} must be Selection")
            self.assertFalse(f.required, f"{field_name} must be optional")
            self.assertFalse(f.index, f"{field_name} must not be indexed")
            self.assertFalse(f.default, f"{field_name} must not have automatic default")

        # Handling fields
        self.assertEqual(WPL._fields["stackable"].type, "boolean")
        self.assertFalse(WPL._fields["stackable"].required)
        self.assertFalse(WPL._fields["stackable"].index)

        self.assertEqual(WPL._fields["max_stack"].type, "integer")
        self.assertFalse(WPL._fields["max_stack"].required)
        self.assertFalse(WPL._fields["max_stack"].index)

        self.assertEqual(WPL._fields["fragile"].type, "boolean")
        self.assertFalse(WPL._fields["fragile"].required)
        self.assertFalse(WPL._fields["fragile"].index)

    # ------------------------------------------------------------------
    # TEST-PLM-032: Catálogos Selection exactos
    # ------------------------------------------------------------------

    def test_plm_032_selection_catalogs(self):
        """PLM-004-032: claves exactas de los 4 catálogos Selection."""
        WPL = self.env["wms.product.logistics"]

        # abc_class: A, B, C
        abc_keys = {k for k, _ in WPL._fields["abc_class"].selection}
        self.assertEqual(abc_keys, {"A", "B", "C"})

        # velocity_class: FAST, MEDIUM, SLOW, DEAD
        velocity_keys = {k for k, _ in WPL._fields["velocity_class"].selection}
        self.assertEqual(velocity_keys, {"FAST", "MEDIUM", "SLOW", "DEAD"})

        # temperature_class: AMBIENT, CHILLED, FROZEN, ULTRA_FROZEN
        temp_keys = {k for k, _ in WPL._fields["temperature_class"].selection}
        self.assertEqual(temp_keys, {"AMBIENT", "CHILLED", "FROZEN", "ULTRA_FROZEN"})

        # hazmat_class: NONE, CLASS_1..CLASS_9
        hazmat_keys = {k for k, _ in WPL._fields["hazmat_class"].selection}
        expected_hazmat = {
            "NONE",
            "CLASS_1", "CLASS_2", "CLASS_3",
            "CLASS_4", "CLASS_5", "CLASS_6",
            "CLASS_7", "CLASS_8", "CLASS_9",
        }
        self.assertEqual(hazmat_keys, expected_hazmat)

    # ------------------------------------------------------------------
    # TEST-PLM-033: Perfil no clasificado válido
    # ------------------------------------------------------------------

    def test_plm_033_unclassified_profile_valid(self):
        """PLM-004-033: perfil sin clasificar tiene todos los campos en False/0."""
        profile = self.WPL.create({
            "product_tmpl_id": self.product_1.id,
        })
        self.assertTrue(profile.id)
        self.assertFalse(profile.abc_class)
        self.assertFalse(profile.velocity_class)
        self.assertFalse(profile.temperature_class)
        self.assertFalse(profile.hazmat_class)
        self.assertFalse(profile.stackable)
        self.assertEqual(profile.max_stack, 0)
        self.assertFalse(profile.fragile)

    # ------------------------------------------------------------------
    # TEST-PLM-034: Persistencia de clasificaciones
    # ------------------------------------------------------------------

    def test_plm_034_classifications_persist(self):
        """PLM-004-034: combinación válida A/FAST/CHILLED/CLASS_3 persiste."""
        profile = self.WPL.create({
            "product_tmpl_id": self.product_2.id,
            "abc_class": "A",
            "velocity_class": "FAST",
            "temperature_class": "CHILLED",
            "hazmat_class": "CLASS_3",
        })
        self.assertEqual(profile.abc_class, "A")
        self.assertEqual(profile.velocity_class, "FAST")
        self.assertEqual(profile.temperature_class, "CHILLED")
        self.assertEqual(profile.hazmat_class, "CLASS_3")

    # ------------------------------------------------------------------
    # TEST-PLM-035: hazmat NONE vs False y limpieza
    # ------------------------------------------------------------------

    def test_plm_035_hazmat_none_and_clear(self):
        """PLM-004-035: hazmat NONE es distinto de False y clasificaciones pueden limpiarse."""
        profile = self.WPL.create({
            "product_tmpl_id": self.product_3.id,
            "hazmat_class": "NONE",
            "abc_class": "B",
        })
        self.assertEqual(profile.hazmat_class, "NONE")
        self.assertIsNot(profile.hazmat_class, False)

        # Limpiar clasificaciones
        profile.write({
            "abc_class": False,
            "velocity_class": False,
            "temperature_class": False,
            "hazmat_class": False,
        })
        self.assertFalse(profile.abc_class)
        self.assertFalse(profile.velocity_class)
        self.assertFalse(profile.temperature_class)
        self.assertFalse(profile.hazmat_class)

    # ------------------------------------------------------------------
    # TEST-PLM-036: Atributos de manejo válidos e independencia de fragile
    # ------------------------------------------------------------------

    def test_plm_036_valid_handling_attributes(self):
        """PLM-004-036: stackable=True/max_stack>=2; fragile es independiente."""
        # Apilable + Frágil
        p1 = self.PT.create({"name": "Handling P1", "company_id": self.company.id})
        profile1 = self.WPL.create({
            "product_tmpl_id": p1.id,
            "stackable": True,
            "max_stack": 3,
            "fragile": True,
        })
        self.assertTrue(profile1.stackable)
        self.assertEqual(profile1.max_stack, 3)
        self.assertTrue(profile1.fragile)

        # No apilable + Frágil
        p2 = self.PT.create({"name": "Handling P2", "company_id": self.company.id})
        profile2 = self.WPL.create({
            "product_tmpl_id": p2.id,
            "stackable": False,
            "max_stack": 0,
            "fragile": True,
        })
        self.assertFalse(profile2.stackable)
        self.assertEqual(profile2.max_stack, 0)
        self.assertTrue(profile2.fragile)

        # Apilable + No frágil (mínimo 2 niveles)
        p3 = self.PT.create({"name": "Handling P3", "company_id": self.company.id})
        profile3 = self.WPL.create({
            "product_tmpl_id": p3.id,
            "stackable": True,
            "max_stack": 2,
            "fragile": False,
        })
        self.assertTrue(profile3.stackable)
        self.assertEqual(profile3.max_stack, 2)
        self.assertFalse(profile3.fragile)

    # ------------------------------------------------------------------
    # TEST-PLM-037: max_stack negativo rechazado por DB
    # ------------------------------------------------------------------

    def test_plm_037_negative_max_stack_rejected(self):
        """PLM-004-037: DB CHECK constraint rechaza max_stack < 0."""
        p = self.PT.create({"name": "Negative Stack Product", "company_id": self.company.id})

        with self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.WPL.create({
                    "product_tmpl_id": p.id,
                    "max_stack": -1,
                })

    # ------------------------------------------------------------------
    # TEST-PLM-038: Coherencia semántica stackable ↔ max_stack
    # ------------------------------------------------------------------

    def test_plm_038_stackability_consistency(self):
        """PLM-004-038: coherencia entre stackable y max_stack en create y write."""
        p_invalid_1 = self.PT.create({"name": "Consistency P1", "company_id": self.company.id})
        p_invalid_2 = self.PT.create({"name": "Consistency P2", "company_id": self.company.id})
        p_invalid_3 = self.PT.create({"name": "Consistency P3", "company_id": self.company.id})

        # stackable=False con max_stack > 0 -> reject
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": p_invalid_1.id,
                "stackable": False,
                "max_stack": 3,
            })

        # stackable=True con max_stack = 0 -> reject
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": p_invalid_2.id,
                "stackable": True,
                "max_stack": 0,
            })

        # stackable=True con max_stack = 1 -> reject (apilar requiere al menos 2)
        with self.assertRaises(ValidationError):
            self.WPL.create({
                "product_tmpl_id": p_invalid_3.id,
                "stackable": True,
                "max_stack": 1,
            })

        # Cambios coordinados vía write
        p_valid = self.PT.create({"name": "Consistency Valid", "company_id": self.company.id})
        profile = self.WPL.create({
            "product_tmpl_id": p_valid.id,
            "stackable": False,
            "max_stack": 0,
        })

        # Pasar a apilable coordinadamente
        profile.write({
            "stackable": True,
            "max_stack": 4,
        })
        self.assertTrue(profile.stackable)
        self.assertEqual(profile.max_stack, 4)

        # Volver a no apilable coordinadamente
        profile.write({
            "stackable": False,
            "max_stack": 0,
        })
        self.assertFalse(profile.stackable)
        self.assertEqual(profile.max_stack, 0)
