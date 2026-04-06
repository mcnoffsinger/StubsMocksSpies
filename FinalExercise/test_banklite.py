from banklite import PaymentProcessor, Transaction, FraudAwareProcessor
import unittest
from unittest.mock import MagicMock


class TestPaymentProsessor(unittest.TestCase):
    def setUp(self):
        self.gateway = MagicMock()
        self.audit   = MagicMock()
        self.proc    = PaymentProcessor(self.gateway, self.audit)

    def _make_tx(self, amount=100.00, tx_id="TX-001", user_id=1):

        """Helper: build a Transaction. Keeps test setup DRY.

        Default values mean each test only specifies what it cares about."""

        return Transaction(tx_id=tx_id, user_id=user_id, amount=amount)


    def test_process_returns_success_when_gateway_charges(self):
        self.gateway.charge.return_value = True
        self.assertEqual( self.proc.process(self._make_tx()), "success")


    def test_process_returns_declined_when_gateway_rejects(self):
        self.gateway.charge.return_value = False
        self.assertEqual( self.proc.process(self._make_tx()), "declined")

    def test_process_raises_on_zero_amount(self):
        with self.assertRaises(ValueError):
            self.proc.process(self._make_tx(amount = 0))
        self.gateway.charge.assert_not_called()
        self.audit.record.assert_not_called()



    def test_process_raises_on_negative_amount(self):
        with self.assertRaises(ValueError):
            self.proc.process(self._make_tx(amount = -30))
        self.gateway.charge.assert_not_called()
        self.audit.record.assert_not_called()



    def test_process_raises_when_amount_exceeds_limit(self):
        with self.assertRaises(ValueError):
            self.proc.process(self._make_tx(amount = 10000030))
        self.gateway.charge.assert_not_called()
        self.audit.record.assert_not_called()


    def test_process_accepts_amount_at_max_limit(self):
        self.gateway.charge.return_value = True
        self.assertEqual( self.proc.process(self._make_tx(amount = 10_000.00)), "success")



    def test_audit_records_charged_event_on_success(self):
        tx = self._make_tx()
        self.proc.process(tx)
        self.audit.record.assert_called_once_with(
        "CHARGED", tx.tx_id, {"amount": tx.amount}
        )



    def test_audit_records_declined_event_on_failure(self):
        tx = self._make_tx()
        self.gateway.charge.return_value = False
        self.proc.process(tx)
        self.audit.record.assert_called_once_with(
        "DECLINED", tx.tx_id, {"amount": tx.amount}
        )



    def test_audit_not_called_when_validation_fails(self):
        with self.assertRaises(ValueError):
            self.proc.process(self._make_tx(amount = 0))
        self.audit.record.assert_not_called()
        


class TestFraudAwareProcessor(unittest.TestCase):
    def setUp(self):
        self.gateway =  MagicMock()
        self.mailer =   MagicMock()
        self.detector = MagicMock()
        self.audit   =  MagicMock()
        self.proc    = FraudAwareProcessor(self.gateway, self.detector, self.mailer, self.audit)
