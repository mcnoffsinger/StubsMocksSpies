from banklite import PaymentProcessor, Transaction, FraudAwareProcessor
from banklite import FraudCheckResult
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
        

###########################TASK TWO #################################
class TestFraudAwareProcessor(unittest.TestCase):
    def setUp(self):
        self.gateway =  MagicMock()
        self.mailer =   MagicMock()
        self.detector = MagicMock()
        self.audit   =  MagicMock()
        self.proc    = FraudAwareProcessor(self.gateway, self.detector, self.mailer, self.audit)

    def _safe_result(self, risk_score = 0.1):
        return FraudCheckResult(approved = True, risk_score=risk_score)
    
    def _fraud_result(self, risk_score = 0.9):
        return FraudCheckResult(approved = False, risk_score = risk_score, reason = "Suspicious")
    
    def _make_tx(self, tx_id = "TX-F01", user_id = 42, amount = 500.00):
        return Transaction(tx_id = tx_id, user_id = user_id, amount = amount)
    
    #actual test cases

    def test_high_risk_returns_blocked(self):
        self.detector.check.return_value = self._fraud_result(risk_score = 0.9)
        fake_tx = self._make_tx()
        self.assertEqual(self.proc.process(fake_tx), "blocked")

    def test_high_risk_does_not_charge_the_card(self):
        self.detector.check.return_value = self._fraud_result(risk_score = 0.9)
        fake_tx = self._make_tx()
        self.proc.process(fake_tx)
        self.gateway.charge.assert_not_called()

    def test_exactly_at_threshold_is_treated_as_fraud(self):
        self.detector.check.return_value = self._fraud_result(risk_score = 0.75)
        fake_tx = self._make_tx()
        self.assertEqual(self.proc.process(fake_tx), "blocked")
    
    def test_just_below_threshold_is_not_blocked(self):
        self.detector.check.return_value = self._fraud_result(risk_score = 0.74)
        fake_tx = self._make_tx()
        self.assertEqual(self.proc.process(fake_tx), "success")
    
    def test_fraud_alert_email_sent_with_correct_args(self):
        self.detector.check.return_value = self._fraud_result(risk_score = 0.76)
        fake_tx = self._make_tx(tx_id="TX-FRAUD", user_id=67)
        self.proc.process(fake_tx)

        self.mailer.send_fraud_alert.assert_called_once_with(67, "TX-FRAUD")

    def test_fraud_audit_records_blocked_event(self):
        self.detector.check.return_value = self._fraud_result(risk_score = 0.88)
        fake_tx = self._make_tx(tx_id="TX-BLK", user_id=67)
        self.proc.process(fake_tx)

        self.audit.record.assert_called_once_with(
            "BLOCKED", "TX-BLK", {"risk": 0.88}
        )
    
    def test_low_risk_successful_charge_returns_success(self):
        self.detector.check.return_value = self._safe_result()    
        self.gateway.charge.return_value = True                   
        fake_tx = self._make_tx()

        result = self.proc.process(fake_tx)
        self.assertEqual(result, "success")

    def test_receipt_email_sent_on_successful_charge(self):
        self.detector.check.return_value = self._safe_result()    
        self.gateway.charge.return_value = True                   
        fake_tx = self._make_tx(tx_id="TX-good", user_id=67)
        self.proc.process(fake_tx)


        self.mailer.send_receipt.assert_called_once_with(67, "TX-good", 500.00)

    def test_fraud_alert_not_sent_on_successful_charge(self):
        self.detector.check.return_value = self._safe_result()    
        self.gateway.charge.return_value = True                   
        fake_tx = self._make_tx(tx_id="TX-good", user_id=67)
        self.proc.process(fake_tx)

        self.mailer.send_fraud_alert.assert_not_called()

    def test_low_risk_declined_charge_returns_declined(self):
        self.detector.check.return_value = self._safe_result()    
        self.gateway.charge.return_value = False                 
        fake_tx = self._make_tx(tx_id="TX-declined", user_id=67)
        result = self.proc.process(fake_tx)

        self.assertEqual(result, "declined")

    def test_receipt_not_sent_on_declined_charge(self):
        self.detector.check.return_value = self._safe_result()    
        self.gateway.charge.return_value = False                 
        fake_tx = self._make_tx(tx_id="TX-declined", user_id=67)
        self.proc.process(fake_tx)

        self.mailer.send_receipt.assert_not_called()
    
    def test_fraud_detector_connection_error_propagates(self):
        self.detector.check.side_effect = ConnectionError("Fraud API is down")
        fake_tx = self._make_tx()


        with self.assertRaises(ConnectionError):
            self.proc.process(fake_tx)


    
################# TASK THREE ########################################
    

    

    
    
    