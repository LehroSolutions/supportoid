import pytest
from src.agents.classifier import IntentClassifier
from src.config.settings import Settings


def test_probability_winner_preserves_naive_bayes_predictions():
    classifier = IntentClassifier(Settings())
    for message in ["Reset my password", "Please refund the duplicate charge", "Production is down!", "Thanks for your help", "Bonjour", "98765"]:
        expected = classifier.pipeline.predict([message])[0]
        probabilities = classifier.pipeline.predict_proba([message])[0]
        result = classifier.classify(message)
        assert result["intent"] == expected
        assert result["confidence"] == round(float(max(probabilities)), 4)
        assert sum(result["all_intents"].values()) == pytest.approx(1)
