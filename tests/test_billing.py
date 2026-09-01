from decimal import Decimal
from unittest import TestCase

from app.billing import billable_output_tokens, calculate_charge, fallback_charge
from app.models import Usage


class _Settings:
    credits_per_usd = 10000
    price_input_per_million_usd = Decimal("2.00")
    price_output_per_million_usd = Decimal("6.00")
    commission_percent = Decimal("30")
    commission_flat_usd = Decimal("0")
    min_charge_credits = 1
    fallback_charge_credits = 10


class BillingTests(TestCase):
    def test_typical_turn(self) -> None:
        usage = Usage(prompt_tokens=1000, completion_tokens=500)
        charge = calculate_charge(usage, _Settings())
        # provider = 1000/1e6*2 + 500/1e6*6 = 0.002 + 0.003 = 0.005
        # billed = 0.005 * 1.3 = 0.0065
        # credits = ceil(65) = 65
        self.assertEqual(charge.provider_cost_usd, "0.00500000")
        self.assertEqual(charge.billed_usd, "0.00650000")
        self.assertEqual(charge.markup_usd, "0.00150000")
        self.assertEqual(charge.credits_charged, 65)

    def test_min_charge(self) -> None:
        usage = Usage(prompt_tokens=1, completion_tokens=0)
        charge = calculate_charge(usage, _Settings())
        self.assertGreaterEqual(charge.credits_charged, 1)
        self.assertEqual(charge.credits_charged, 1)

    def test_reasoning_subset_not_double_counted(self) -> None:
        usage = Usage(
            prompt_tokens=0,
            completion_tokens=100,
            reasoning_tokens=40,
        )
        self.assertEqual(billable_output_tokens(usage), 100)
        charge = calculate_charge(usage, _Settings())
        # output 100 / 1e6 * 6 = 0.0006; billed = 0.00078; credits = ceil(7.8) = 8
        self.assertEqual(charge.credits_charged, 8)

    def test_reasoning_extra_added(self) -> None:
        usage = Usage(
            prompt_tokens=0,
            completion_tokens=50,
            reasoning_tokens=200,
        )
        self.assertEqual(billable_output_tokens(usage), 250)
        charge = calculate_charge(usage, _Settings())
        # output 250/1e6*6 = 0.0015; billed = 0.00195; credits = ceil(19.5) = 20
        self.assertEqual(charge.credits_charged, 20)

    def test_flat_commission(self) -> None:
        class Flat(_Settings):
            commission_percent = Decimal("0")
            commission_flat_usd = Decimal("0.01")

        usage = Usage(prompt_tokens=0, completion_tokens=0)
        charge = calculate_charge(usage, Flat())
        # billed = 0.01; credits = ceil(100) = 100
        self.assertEqual(charge.billed_usd, "0.01000000")
        self.assertEqual(charge.credits_charged, 100)

    def test_fallback_charge(self) -> None:
        charge = fallback_charge(_Settings())
        self.assertEqual(charge.credits_charged, 10)
        self.assertEqual(charge.billed_usd, "0.00100000")

    def test_ceil_fractional_credits(self) -> None:
        usage = Usage(prompt_tokens=1, completion_tokens=1)
        charge = calculate_charge(usage, _Settings())
        # provider = 2/1e6 + 6/1e6 = 0.000008
        # billed = 0.0000104
        # credits = ceil(0.104) -> min 1
        self.assertEqual(charge.credits_charged, 1)
