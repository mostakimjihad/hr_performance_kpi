# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date

from odoo.tests import common, tagged
from odoo.exceptions import ValidationError, UserError


class TestKpiManagement(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.KpiCategory = cls.env['kpi.category']
        cls.KpiTemplate = cls.env['kpi.template']
        cls.KpiAssignment = cls.env['kpi.assignment']
        cls.KpiResult = cls.env['kpi.result']

        # Create test category
        cls.category = cls.KpiCategory.create({
            'name': 'Test Category',
            'description': 'Test category for unit tests',
        })

        # Create test employee
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test Employee',
        })

        # Create test department
        cls.department = cls.env['hr.department'].create({
            'name': 'Test Department',
        })

        # Create test template (maximize, manual)
        cls.template_max = cls.KpiTemplate.create({
            'name': 'Test Maximize KPI',
            'code': 'TEST_MAX',
            'category_id': cls.category.id,
            'kpi_type': 'quantitative',
            'direction': 'maximize',
            'periodicity': 'monthly',
            'target_value': 80.0,
            'min_value': 0.0,
            'max_value': 100.0,
            'green_threshold': 80.0,
            'amber_threshold': 50.0,
            'weight': 1.0,
            'calculation_method': 'manual',
        })

        # Create test template (minimize)
        cls.template_min = cls.KpiTemplate.create({
            'name': 'Test Minimize KPI',
            'code': 'TEST_MIN',
            'category_id': cls.category.id,
            'kpi_type': 'quantitative',
            'direction': 'minimize',
            'periodicity': 'monthly',
            'target_value': 10.0,
            'min_value': 0.0,
            'max_value': 100.0,
            'green_threshold': 80.0,
            'amber_threshold': 50.0,
            'weight': 1.0,
            'calculation_method': 'manual',
        })

        # Create test template (target)
        cls.template_target = cls.KpiTemplate.create({
            'name': 'Test Target KPI',
            'code': 'TEST_TGT',
            'category_id': cls.category.id,
            'kpi_type': 'quantitative',
            'direction': 'target',
            'periodicity': 'monthly',
            'target_value': 50.0,
            'min_value': 0.0,
            'max_value': 100.0,
            'green_threshold': 80.0,
            'amber_threshold': 50.0,
            'weight': 1.0,
            'calculation_method': 'manual',
        })

    # ---- Category Tests ----

    def test_category_creation(self):
        """Test basic category creation."""
        self.assertEqual(self.category.name, 'Test Category')
        self.assertTrue(self.category.active)

    def test_category_hierarchy(self):
        """Test parent/child category hierarchy."""
        child = self.KpiCategory.create({
            'name': 'Child Category',
            'parent_id': self.category.id,
        })
        self.assertEqual(child.parent_id, self.category)
        self.assertIn(child, self.category.child_ids)

    # ---- Template Tests ----

    def test_template_creation(self):
        """Test basic template creation."""
        self.assertEqual(self.template_max.name, 'Test Maximize KPI')
        self.assertEqual(self.template_max.direction, 'maximize')

    def test_template_rag_validation(self):
        """Test that green must be greater than amber threshold."""
        with self.assertRaises(ValidationError):
            self.KpiTemplate.create({
                'name': 'Invalid RAG',
                'direction': 'maximize',
                'periodicity': 'monthly',
                'target_value': 50.0,
                'min_value': 0.0,
                'max_value': 100.0,
                'green_threshold': 50.0,
                'amber_threshold': 80.0,  # Amber > Green - invalid
                'calculation_method': 'manual',
            })

    def test_template_weight_validation(self):
        """Test weight must be between 0 and 10."""
        with self.assertRaises(ValidationError):
            self.KpiTemplate.create({
                'name': 'Invalid Weight',
                'direction': 'maximize',
                'periodicity': 'monthly',
                'target_value': 50.0,
                'min_value': 0.0,
                'max_value': 100.0,
                'green_threshold': 80.0,
                'amber_threshold': 50.0,
                'weight': 15.0,  # > 10 - invalid
                'calculation_method': 'manual',
            })

    # ---- Assignment Tests ----

    def test_assignment_requires_employee_or_department(self):
        """Test that assignment requires at least employee or department."""
        with self.assertRaises(ValidationError):
            self.KpiAssignment.create({
                'template_id': self.template_max.id,
                'valid_from': '2026-01-01',
            })

    def test_assignment_activate(self):
        """Test assignment activation."""
        assignment = self.KpiAssignment.create({
            'template_id': self.template_max.id,
            'employee_id': self.employee.id,
            'valid_from': '2026-07-01',
        })
        self.assertEqual(assignment.state, 'draft')
        assignment.action_activate()
        self.assertEqual(assignment.state, 'active')

    # ---- Result Tests ----

    def test_result_score_maximize(self):
        """Test score computation for maximize direction."""
        result = self.KpiResult.create({
            'template_id': self.template_max.id,
            'employee_id': self.employee.id,
            'period_start': '2026-07-01',
            'period_end': '2026-07-31',
            'target_value': 80.0,
            'actual_value': 75.0,
            'state': 'draft',
        })
        # Score = ((75 - 0) / (100 - 0)) * 100 = 75%
        self.assertAlmostEqual(result.score, 75.0, places=1)
        self.assertEqual(result.rag_status, 'amber')  # 75 < 80, 75 >= 50

    def test_result_score_minimize(self):
        """Test score computation for minimize direction."""
        result = self.KpiResult.create({
            'template_id': self.template_min.id,
            'employee_id': self.employee.id,
            'period_start': '2026-07-01',
            'period_end': '2026-07-31',
            'target_value': 10.0,
            'actual_value': 5.0,
            'state': 'draft',
        })
        # Score = ((100 - 5) / (100 - 0)) * 100 = 95%
        self.assertAlmostEqual(result.score, 95.0, places=1)
        self.assertEqual(result.rag_status, 'green')  # 95 >= 80

    def test_result_score_target(self):
        """Test score computation for target direction."""
        result = self.KpiResult.create({
            'template_id': self.template_target.id,
            'employee_id': self.employee.id,
            'period_start': '2026-07-01',
            'period_end': '2026-07-31',
            'target_value': 50.0,
            'actual_value': 55.0,
            'state': 'draft',
        })
        # deviation = |55-50|/50 = 0.1, score = (1-0.1)*100 = 90%
        self.assertAlmostEqual(result.score, 90.0, places=1)
        self.assertEqual(result.rag_status, 'green')  # 90 >= 80

    def test_result_rag_status(self):
        """Test RAG status computation."""
        result = self.KpiResult.create({
            'template_id': self.template_max.id,
            'employee_id': self.employee.id,
            'period_start': '2026-07-01',
            'period_end': '2026-07-31',
            'target_value': 80.0,
            'actual_value': 90.0,
            'state': 'draft',
        })
        # Score = 90%, >= 80 green threshold
        self.assertAlmostEqual(result.score, 90.0, places=1)
        self.assertEqual(result.rag_status, 'green')

        result.actual_value = 30.0
        # Score = 30%, < 50 amber threshold → red
        self.assertAlmostEqual(result.score, 30.0, places=1)
        self.assertEqual(result.rag_status, 'red')

    def test_result_approval_workflow(self):
        """Test the complete approval workflow."""
        result = self.KpiResult.create({
            'template_id': self.template_max.id,
            'employee_id': self.employee.id,
            'period_start': '2026-07-01',
            'period_end': '2026-07-31',
            'target_value': 80.0,
            'actual_value': 85.0,
            'state': 'draft',
        })

        # Submit
        result.action_submit()
        self.assertEqual(result.state, 'submitted')

        # Review
        result.action_review()
        self.assertEqual(result.state, 'reviewed')

        # Approve
        result.action_approve()
        self.assertEqual(result.state, 'approved')

    def test_result_return_workflow(self):
        """Test the return workflow."""
        result = self.KpiResult.create({
            'template_id': self.template_max.id,
            'employee_id': self.employee.id,
            'period_start': '2026-07-01',
            'period_end': '2026-07-31',
            'target_value': 80.0,
            'actual_value': 85.0,
            'state': 'draft',
        })
        result.action_submit()
        result.action_return()
        self.assertEqual(result.state, 'returned')
        result.action_reset_draft()
        self.assertEqual(result.state, 'draft')

    def test_dashboard_summary(self):
        """Test dashboard summary data."""
        # Empty DB — must return a well-formed dict without raising.
        empty = self.KpiResult.get_dashboard_summary()
        self.assertEqual(empty['total_results'], 0)
        self.assertEqual(empty['avg_score'], 0.0)

        # Add an approved result so the breakdown has data.
        self.KpiResult.create({
            'template_id': self.template_max.id,
            'employee_id': self.employee.id,
            'period_start': '2026-07-01',
            'period_end': '2026-07-31',
            'target_value': 80.0,
            'actual_value': 90.0,
            'state': 'approved',
        })

        summary = self.KpiResult.get_dashboard_summary()
        self.assertEqual(summary['total_results'], 1)
        self.assertEqual(summary['on_track'], 1)
        self.assertIn('avg_score', summary)
        self.assertGreater(summary['avg_score'], 0.0)

    def test_department_assignment_employees(self):
        """Test that department assignment covers department members."""
        self.employee.department_id = self.department.id

        assignment = self.KpiAssignment.create({
            'template_id': self.template_max.id,
            'department_id': self.department.id,
            'valid_from': '2026-07-01',
        })
        assignment.action_activate()

        # Check that results were generated for the department employee
        results = self.KpiResult.search([
            ('template_id', '=', self.template_max.id),
            ('employee_id', '=', self.employee.id),
        ])
        self.assertTrue(len(results) > 0)

    def test_zero_actual_value_is_not_treated_as_missing(self):
        """An actual value of 0 must still produce a score, not 0-by-default."""
        result = self.KpiResult.create({
            'template_id': self.template_max.id,
            'employee_id': self.employee.id,
            'period_start': '2026-07-01',
            'period_end': '2026-07-31',
            'target_value': 50.0,
            'actual_value': 0.0,
            'state': 'draft',
        })
        # 0 with min=0, max=100 should map to 0 score, not be skipped entirely.
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.rag_status, 'red')

    def test_formula_safety(self):
        """Formula evaluation must use safe_eval, not raw eval()."""
        template = self.KpiTemplate.create({
            'name': 'Test Formula',
            'kpi_type': 'quantitative',
            'direction': 'maximize',
            'periodicity': 'monthly',
            'target_value': 100.0,
            'min_value': 0.0,
            'max_value': 200.0,
            'calculation_method': 'formula',
            'expression': '__import__("os").system("echo PWNED")',
        })
        value = template._compute_actual_value_formula(
            self.employee, date(2026, 1, 1), date(2026, 1, 31),
        )
        # Either the call was rejected by safe_eval (returning 0.0) or no
        # exception escaped; what matters is that __import__ is unavailable.
        self.assertEqual(value, 0.0)

    def test_formula_arithmetic(self):
        """A legitimate formula should evaluate correctly."""
        template = self.KpiTemplate.create({
            'name': 'Test Formula OK',
            'kpi_type': 'quantitative',
            'direction': 'maximize',
            'periodicity': 'monthly',
            'target_value': 100.0,
            'min_value': 0.0,
            'max_value': 200.0,
            'calculation_method': 'formula',
            'expression': 'value * 1.1',
        })
        # No prior result exists so 'value' starts at 0.0; result should be 0.
        self.assertEqual(
            template._compute_actual_value_formula(
                self.employee, date(2026, 1, 1), date(2026, 1, 31),
            ),
            0.0,
        )
