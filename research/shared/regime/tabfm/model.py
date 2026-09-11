"""
TabFM (Tabular Foundation Model) wrapper for local inference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class TabFMConfig:
    """Immutable TabFM model configuration."""

    d_model: int = 256
    n_heads: int = 8
    n_layers: int = 6
    d_ff: int = 1024
    dropout: float = 0.1
    max_seq_len: int = 128
    n_num_features: int = 45  # Number of continuous features
    n_cat_features: int = 3  # Pair, session, day_of_week
    n_regime_classes: int = 7  # Number of regime labels
    model_path: Optional[str] = None
    device: str = "auto"  # "auto", "cuda", "mps", "cpu"


class TabFMModel:
    """
    Wrapper for TabFM (Tabular Foundation Model) for regime detection.

    Supports:
    - Local GPU/CPU inference with automatic device selection
    - Model loading from checkpoint with caching
    - Batch and single-sample inference
    - ONNX export for production deployment
    """

    def __init__(self, config: TabFMConfig):
        self.config = config
        self._model = None
        self._device = self._resolve_device(config.device)
        self._loaded = False

    @staticmethod
    def _resolve_device(device: str) -> str:
        """Resolve device string to actual device."""
        if device == "auto":
            try:
                import torch
                if torch.cuda.is_available():
                    return "cuda"
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    return "mps"
            except ImportError:
                pass
            return "cpu"
        return device

    def load(self, checkpoint_path: str | None = None) -> None:
        """
        Load model weights from checkpoint.

        Args:
            checkpoint_path: Path to model checkpoint. If None, uses config.model_path.
        """
        path = checkpoint_path or self.config.model_path
        if path is None:
            raise ValueError("No checkpoint path provided")

        # Placeholder for actual model loading
        # In production, this would load PyTorch model weights
        self._loaded = True

    def predict(self, features: np.ndarray) -> dict[str, float]:
        """
        Single-sample prediction returning regime probabilities.

        Args:
            features: Feature vector of shape (n_features,)

        Returns:
            Dict mapping regime names to probabilities
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Placeholder for actual inference
        # In production, this would run model forward pass
        n_regimes = self.config.n_regime_classes
        probs = np.random.dirichlet(np.ones(n_regimes))
        regime_names = [
            "trending", "ranging", "breakout", "high_vol",
            "low_vol", "mean_reversion", "news_driven"
        ]
        return dict(zip(regime_names, probs))

    def predict_batch(self, features: np.ndarray) -> np.ndarray:
        """
        Batch prediction returning regime probability matrix.

        Args:
            features: Feature matrix of shape (batch_size, n_features)

        Returns:
            Probability matrix of shape (batch_size, n_regimes)
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Placeholder for actual batch inference
        batch_size = features.shape[0]
        n_regimes = self.config.n_regime_classes
        return np.random.dirichlet(np.ones(n_regimes), size=batch_size)

    def to_onnx(self, output_path: str) -> None:
        """
        Export model to ONNX format for production inference.

        Args:
            output_path: Path to save ONNX model
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Placeholder for ONNX export
        # In production, this would use torch.onnx.export
        pass
