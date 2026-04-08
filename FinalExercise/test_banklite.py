from banklite import PaymentProcessor, Transaction, FraudAwareProcessor
from banklite import FraudCheckResult, StatementBuilder, PaymentGateway, FeeCalculator, CheckoutService
import unittest
from unittest.mock import MagicMock, patch, call


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
    

class TestStatementBuilder(unittest.TestCase):
    def setUp(self):
        self.repo    = MagicMock()
        self.builder = StatementBuilder(self.repo)


    def test_empty_transaction_list_returns_zero_totals(self):
        self.repo.find_by_user.return_value = []
        result = self.builder.build(user_id = 67)

        self.assertEqual(result["count"], 0)
        self.assertEqual(result["total_charged"], 0.0)
        self.assertIsInstance(result["transactions"], list) 

    def test_only_success_transactions_are_counted_in_total(self):
        
        txlist = [
            Transaction("TX1", 67, 100.00, status="success"),
            Transaction("TX2", 67,  50.00, status="declined"),  
            Transaction("TX3", 67, 200.00, status="success"),
            Transaction("TX4", 67,  75.00, status="pending"), 
        ]
        self.repo.find_by_user.return_value = txlist

        result = self.builder.build(user_id=67)

        self.assertEqual(result["total_charged"], 300.00)  
        self.assertEqual(result["count"], 4)               

    def test_all_success_transactions_summed(self):
       
        txlist = [
            Transaction("TX1", 666, 99.99,  status="success"),
            Transaction("TX2", 666,  0.01,  status="success"), 
            Transaction("TX3", 666, 450.00, status="success"),
        ]
        self.repo.find_by_user.return_value = txlist

        result = self.builder.build(user_id=666)

        self.assertEqual(result["total_charged"], 550.00)  # 99.99 + 0.01 + 450

    def test_total_is_rounded_to_two_decimal_places(self):
        
        
        txlist = [
            Transaction("TX1", 3, 10.555, status="success"),
            Transaction("TX2", 3,  0.005, status="success"),
        ]
        self.repo.find_by_user.return_value = txlist

        result = self.builder.build(user_id=3)

        self.assertEqual(result["total_charged"], 10.56)  # 10.555 + 0.005, rounded

    def test_transactions_list_is_returned_unchanged(self):
        
        txlist = [Transaction("TX1", 4, 100.00, status="success")]
        self.repo.find_by_user.return_value = txlist

        result = self.builder.build(user_id=4)

        self.assertIs(result["transactions"], txlist)


################## TASK 4 ####################################
class TestStretchChallenges(unittest.TestCase):
    def setUp(self):
        real_calc      = FeeCalculator()
        self.spy_calc  = MagicMock(wraps=real_calc)   # this is a spy not a mock
        self.gateway   = MagicMock()
        self.gateway.charge.return_value = True
        self.svc       = CheckoutService(self.spy_calc, self.gateway)

    def _usd_tx(self, amount=100.00):
        return Transaction(tx_id="TX-USD", user_id=1, amount=amount, currency="USD")

    def _eur_tx(self, amount=200.00):
        return Transaction(tx_id="TX-EUR", user_id=1, amount=amount, currency="EUR")
    

    #######tests 
    def test_usd_processing_fee_is_correct(self):
        
        result = self.svc.checkout(self._usd_tx())

        self.assertEqual(result["fee"], 3.20)

    def test_international_fee_includes_surcharge(self):

        result = self.svc.checkout(self._eur_tx())

        self.assertEqual(result["fee"], 9.10)
    
    def test_net_amount_is_amount_minus_fee(self):

        result = self.svc.checkout(self._usd_tx())

        self.assertEqual(result["net"], round(96.80, 2))

    def test_processing_fee_called_with_correct_amount_and_currency(self):
        
        tx = self._usd_tx()

        self.svc.checkout(tx)

        self.spy_calc.processing_fee.assert_called_once_with(100.00, "USD")
    
    def test_net_amount_called_with_correct_amount_and_currency(self):

        tx = self._eur_tx()

        self.svc.checkout(tx)

        self.spy_calc.net_amount.assert_called_once_with(200.00, "EUR")


    def test_each_fee_method_called_exactly_once_per_checkout(self):

        tx = self._usd_tx(67.00)
        self.svc.checkout(tx)

        self.assertEqual(self.spy_calc.processing_fee.call_count, 1)
        self.assertEqual(self.spy_calc.net_amount.call_count, 1)


    def test_spy_return_matches_fee_in_receipt(self):
        
        receipt = self.svc.checkout(self._usd_tx(1000.00))

        self.assertEqual(receipt["fee"], 29.30)
        
        self.assertEqual(receipt["net"], 970.70)

    def test_partial_spy_on_net_amount_only(self):

        real_calc = FeeCalculator()
        svc       = CheckoutService(real_calc, self.gateway)
        tx        = self._usd_tx(500.00)

        with patch.object(real_calc, "net_amount",
                          wraps=real_calc.net_amount) as spy_net:
            receipt = svc.checkout(tx)

        
        spy_net.assert_called_once_with(500.00, "USD")
       
        self.assertEqual(receipt["net"], 485.20)


    def test_contrast_mock_only_tests_wiring_not_formula(self):
        mock_calc = MagicMock()
        mock_calc.processing_fee.return_value = 5.00   
        mock_calc.net_amount.return_value     = 95.00  

        svc     = CheckoutService(mock_calc, self.gateway)
        receipt = svc.checkout(self._usd_tx())

        
        self.assertEqual(receipt["fee"],    5.00)
        self.assertEqual(receipt["net"],   95.00)
        self.assertEqual(receipt["status"], "success")
        mock_calc.processing_fee.assert_called_once()
    

    '''
    
    
    
    
    
    
    
    
    
    '''