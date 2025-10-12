"""
LEA LSTM Model for FreqAI - Simplified
Based on: Deep Learning in Quantitative Trading (Zhang & Zohren, 2025)
"""
from typing import Any
import torch
import torch.nn as nn

from freqtrade.freqai.base_models.BasePyTorchRegressor import BasePyTorchRegressor
from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
from freqtrade.freqai.torch.PyTorchDataConvertor import (
    DefaultPyTorchDataConvertor,
    PyTorchDataConvertor,
)
from freqtrade.freqai.torch.PyTorchModelTrainer import PyTorchModelTrainer


class SimpleLSTMModel(nn.Module):
    """
    Simple LSTM model that handles 2D input from FreqAI
    """
    def __init__(
        self,
        input_dim: int,
        output_dim: int = 1,
        hidden_dim: int = 128,
        num_layers: int = 2,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        # Single LSTM layer
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0,
            batch_first=True,
        )

        # Simple output layer
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, output_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass - handles 2D input (batch, features)
        """
        # x shape: (batch_size, features)
        # Reshape to (batch_size, 1, features) for LSTM
        if len(x.shape) == 2:
            x = x.unsqueeze(1)  # Add sequence dimension

        # LSTM forward
        lstm_out, _ = self.lstm(x)  # (batch_size, 1, hidden_dim)

        # Take the last output
        last_output = lstm_out[:, -1, :]  # (batch_size, hidden_dim)

        # Final prediction
        output = self.fc(last_output)  # (batch_size, output_dim)

        return output


class LeaTorchLSTM(BasePyTorchRegressor):
    """
    LEA LSTM FreqAI Model - Simplified version

    Implements LSTM-based price prediction.

    Config example:
    {
        "freqai": {
            "model_training_parameters": {
                "hidden": 128,
                "layers": 2,
                "dropout": 0.2,
                "epochs": 10,
                "batch_size": 64,
                "lr": 0.001,
                "weight_decay": 0.0001
            }
        }
    }
    """

    @property
    def data_convertor(self) -> PyTorchDataConvertor:
        return DefaultPyTorchDataConvertor(target_tensor_type=torch.float)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        config = self.freqai_info.get("model_training_parameters", {})

        # Model hyperparameters
        self.hidden_dim: int = config.get("hidden", 128)
        self.num_layers: int = config.get("layers", 2)
        self.dropout: float = config.get("dropout", 0.2)

        # Training hyperparameters
        self.learning_rate: float = config.get("lr", 0.001)
        self.weight_decay: float = config.get("weight_decay", 0.0001)
        self.n_epochs: int = config.get("epochs", 10)
        self.batch_size: int = config.get("batch_size", 64)

    def fit(self, data_dictionary: dict, dk: FreqaiDataKitchen, **kwargs) -> Any:
        """
        Train the LSTM model
        """
        n_features = data_dictionary["train_features"].shape[-1]

        # Create model
        model = SimpleLSTMModel(
            input_dim=n_features,
            output_dim=1,
            hidden_dim=self.hidden_dim,
            num_layers=self.num_layers,
            dropout=self.dropout
        )
        model.to(self.device)

        # Optimizer with weight decay
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=self.learning_rate,
            weight_decay=self.weight_decay
        )

        # Loss function
        criterion = torch.nn.MSELoss()

        # Check if continual learning is activated
        trainer = self.get_init_model(dk.pair)
        if trainer is None:
            trainer = PyTorchModelTrainer(
                model=model,
                optimizer=optimizer,
                criterion=criterion,
                device=self.device,
                data_convertor=self.data_convertor,
                tb_logger=self.tb_logger,
                n_epochs=self.n_epochs,
                batch_size=self.batch_size,
            )

        trainer.fit(data_dictionary, self.splits)
        return trainer
