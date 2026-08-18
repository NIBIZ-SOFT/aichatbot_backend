import unittest
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.ai.safety_rules import AISafetyAndRulesEngine

class TestEnterpriseCore(unittest.TestCase):

    def test_ai_lead_detection(self):
        text = "Hello, my email is client@enterprise.com and phone is +1-555-0199."
        result = AISafetyAndRulesEngine.detect_lead(text)
        self.assertTrue(result["is_lead"])
        self.assertIn("client@enterprise.com", result["emails"])

    def test_human_handover_trigger(self):
        self.assertTrue(AISafetyAndRulesEngine.check_human_handover("I want to speak to human agent please"))
        self.assertFalse(AISafetyAndRulesEngine.check_human_handover("What are your opening hours?"))

    def test_sentiment_scoring(self):
        pos = AISafetyAndRulesEngine.analyze_sentiment("This service is great and awesome, love it!")
        self.assertGreater(pos, 0.0)
        neg = AISafetyAndRulesEngine.analyze_sentiment("This is terrible, broken, and worst support ever.")
        self.assertLess(neg, 0.0)

if __name__ == '__main__':
    unittest.main()
