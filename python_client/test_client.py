"""Verify the Stockfish Docker client can connect to the service."""

import unittest

from python_client.client import StockfishDockerClient


class StockfishDockerClientTest(unittest.TestCase):
    """Smoke test coverage against a live Stockfish container."""

    def setUp(self) -> None:
        self.client = StockfishDockerClient()

    def test_service_readiness_is_boolean(self) -> None:
        self.assertIsInstance(self.client.is_service_ready(), bool)

    def test_prediction_returns_move_and_evaluation(self) -> None:
        if not self.client.is_service_ready():
            self.skipTest("Stockfish container is not running")

        prediction = self.client.predict_next_move(depth=5)
        self.assertTrue(prediction.bestmove)
        self.assertIsInstance(prediction.evaluation.score_value, float)
        self.assertGreaterEqual(prediction.evaluation.depth, 0)
