import unittest
from unittest.mock import MagicMock
from pricing import Product,  DiscountEngine

class TestDiscountEngineWithMock(unittest.TestCase):
    """
    Using a mock instead of a spy. Notice:
    - We must configure every return_value manually
    - The real calculator logic is NEVER tested here
    - If PriceCalculator.discount had a bug, this test wouldn't catch it
    """
    def setUp(self):
        self.mock_calc = MagicMock()
        self.mock_calc.discount.return_value     = 800.00  # hardcoded
        self.mock_calc.category_tax.return_value = 100.00  # hardcoded
        self.engine = DiscountEngine(self.mock_calc)

    def test_total_uses_values_from_calculator(self):
        product = Product("X", 0.0, "electronics")  # base_price irrelevant
        result  = self.engine.apply_sale(product, 0.20)

        # Tests InvoiceService wiring — not calculator correctness
        self.assertEqual(result["total"], 900.00)  # 800 + 100
        self.mock_calc.discount.assert_called_once()