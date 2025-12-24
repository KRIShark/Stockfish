"""Minimal Docker client for Stockfish UCI predictions."""

from __future__ import annotations

import argparse
import dataclasses
import subprocess
from typing import Optional, Sequence


@dataclasses.dataclass(frozen=True)
class Evaluation:
    """Evaluation captured from the last UCI info score."""

    score_type: str
    score_value: float
    depth: int


@dataclasses.dataclass(frozen=True)
class Prediction:
    """Prediction containing a best move plus its evaluation."""

    bestmove: str
    ponder: Optional[str]
    evaluation: Evaluation


class StockfishDockerClient:
    """Run Stockfish inside ``docker exec`` and surface predictions."""

    def __init__(
        self,
        container_name: str = "stockfish-engine",
        engine_cmd: str = "stockfish",
    ) -> None:
        self.container_name = container_name
        self.engine_cmd = engine_cmd

    def is_service_ready(self) -> bool:
        """Check if the Docker container exists and is running."""

        try:
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "-f",
                    "{{.State.Running}}",
                    self.container_name,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

        return result.stdout.strip().lower() == "true"

    def predict_next_move(
        self,
        fen: str = "startpos",
        depth: int = 12,
        moves: Optional[Sequence[str]] = None,
    ) -> Prediction:
        """Ask Stockfish for the next best move and evaluation."""

        prediction = self._query_engine(fen, depth, moves)
        return prediction

    def analyze_position(
        self,
        fen: str = "startpos",
        depth: int = 12,
        moves: Optional[Sequence[str]] = None,
    ) -> Evaluation:
        """Return the latest evaluation for the position."""

        return self._query_engine(fen, depth, moves).evaluation

    def _query_engine(
        self,
        fen: str,
        depth: int,
        moves: Optional[Sequence[str]],
    ) -> Prediction:
        commands: list[str] = ["uci", "isready", "ucinewgame"]
        moves_payload = list(moves) if moves else None

        if moves_payload:
            if fen == "startpos":
                commands.append(f"position startpos moves {' '.join(moves_payload)}")
            else:
                commands.append(f"position fen {fen} moves {' '.join(moves_payload)}")
        elif fen == "startpos":
            commands.append("position startpos")
        else:
            commands.append(f"position fen {fen}")

        commands.append(f"go depth {depth}")

        stderr_output = ""
        try:
            process = subprocess.Popen(
                [
                    "docker",
                    "exec",
                    "-i",
                    self.container_name,
                    self.engine_cmd,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("Docker is not installed or not found in PATH") from exc

        if process.stdin is None or process.stdout is None:
            raise RuntimeError("Failed to open Stockfish stdin/stdout streams")

        try:
            for command in commands:
                process.stdin.write(f"{command}\n")
            process.stdin.flush()

            bestmove: Optional[str] = None
            ponder: Optional[str] = None
            evaluation: Optional[Evaluation] = None
            best_depth = -1

            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue

                if line.startswith("info"):
                    parsed = self._parse_evaluation(line)
                    if parsed and parsed.depth >= best_depth:
                        evaluation = parsed
                        best_depth = parsed.depth
                    continue

                if line.startswith("bestmove"):
                    tokens = line.split()
                    if len(tokens) >= 2:
                        bestmove = tokens[1]
                    if "ponder" in tokens:
                        ponder_index = tokens.index("ponder")
                        if ponder_index + 1 < len(tokens):
                            ponder = tokens[ponder_index + 1]
                    break

            process.stdin.write("quit\n")
            process.stdin.flush()
            _, stderr_output = process.communicate(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()

        if process.returncode not in (0, None):
            raise RuntimeError(f"Stockfish process failed: {stderr_output.strip()}")

        if bestmove is None:
            raise RuntimeError("Stockfish did not report a best move")

        if evaluation is None:
            evaluation = Evaluation(score_type="cp", score_value=0.0, depth=depth)

        return Prediction(bestmove=bestmove, ponder=ponder, evaluation=evaluation)

    @staticmethod
    def _parse_evaluation(raw_line: str) -> Optional[Evaluation]:
        tokens = raw_line.split()
        if "score" not in tokens:
            return None

        try:
            score_index = tokens.index("score")
            score_type = tokens[score_index + 1]
            score_value = tokens[score_index + 2]
        except (ValueError, IndexError):
            return None

        depth = 0
        if "depth" in tokens:
            try:
                depth_index = tokens.index("depth")
                depth_value = tokens[depth_index + 1]
                depth = int(depth_value)
            except (ValueError, IndexError):
                depth = 0

        try:
            if score_type == "cp":
                return Evaluation(score_type=score_type, score_value=int(score_value) / 100.0, depth=depth)
            if score_type == "mate":
                return Evaluation(score_type=score_type, score_value=int(score_value), depth=depth)
            return Evaluation(score_type=score_type, score_value=float(score_value), depth=depth)
        except ValueError:
            return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the Stockfish docker service.")
    parser.add_argument("--fen", default="startpos", help="FEN string for the position.")
    parser.add_argument("--depth", type=int, default=12, help="Search depth.")
    parser.add_argument(
        "--moves",
        nargs="+",
        help="Optional moves to play after the provided FEN (algebraic notation).",
    )
    parser.add_argument(
        "--container-name",
        default="stockfish-engine",
        help="Docker container running the Stockfish engine.",
    )

    args = parser.parse_args()
    client = StockfishDockerClient(container_name=args.container_name)

    if not client.is_service_ready():
        raise RuntimeError("Stockfish container is not running; please start it with docker compose")

    prediction = client.predict_next_move(fen=args.fen, depth=args.depth, moves=args.moves)
    print(f"Best move: {prediction.bestmove}")
    if prediction.ponder:
        print(f"Ponder:     {prediction.ponder}")
    print(f"Depth:      {prediction.evaluation.depth}")
    print(f"Score type: {prediction.evaluation.score_type}")
    print(f"Score:      {prediction.evaluation.score_value}")


if __name__ == "__main__":
    main()
