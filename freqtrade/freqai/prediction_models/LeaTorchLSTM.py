"""
LEA LSTM Model for FreqAI
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


class LSTMWithAttention(nn.Module):
    """
    LSTM model with optional attention mechanism
    """
    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 128,
        num_layers: int = 2,
        dropout: float = 0.25,
        sequence_len: int = 48,
        use_attention: bool = True,
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.use_attention = use_attention

        # LSTM layers
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0,
            batch_first=True,
            bidirectional=False
        )

        # Attention mechanism
        if use_attention:
            self.attention = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim),
                nn.Tanh(),
                nn.Linear(hidden_dim, 1)
            )

        # Output layer
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 1)
        )

    def forward(self, x):
        # x shape: (batch_size, sequence_len, input_dim)
        lstm_out, _ = self.lstm(x)  # (batch_size, sequence_len, hidden_dim)

        if self.use_attention:
            # Attention weights
            attention_weights = self.attention(lstm_out)  # (batch_size, sequence_len, 1)
            attention_weights = torch.softmax(attention_weights, dim=1)

            # Weighted sum
            context = torch.sum(attention_weights * lstm_out, dim=1)  # (batch_size, hidden_dim)
        else:
            # Use last output
            context = lstm_out[:, -1, :]  # (batch_size, hidden_dim)

        # Final prediction
        output = self.fc(context)  # (batch_size, 1)
        return output


class LeaTorchLSTM(BasePyTorchRegressor):
    """
    LEA LSTM FreqAI Model

    Implements LSTM-based price prediction with attention mechanism.

    Config example:
    {
        "freqai": {
            "model_training_parameters": {
                "sequence": 48,
                "hidden": 128,
                "layers": 2,
                "dropout": 0.25,
                "use_attention": true,
                "epochs": 15,
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
        self.sequence_len: int = config.get("sequence", 48)
        self.hidden_dim: int = config.get("hidden", 128)
        self.num_layers: int = config.get("layers", 2)
        self.dropout: float = config.get("dropout", 0.25)
        self.use_attention: bool = config.get("use_attention", True)

        # Training hyperparameters
        self.learning_rate: float = config.get("lr", 0.001)
        self.weight_decay: float = config.get("weight_decay", 0.0001)
        self.n_epochs: int = config.get("epochs", 15)
        self.batch_size: int = config.get("batch_size", 64)

    def fit(self, data_dictionary: dict, dk: FreqaiDataKitchen, **kwargs) -> Any:
        """
        Train the LSTM model
        """
        n_features = data_dictionary["train_features"].shape[-1]

        # Create model
        model = LSTMWithAttention(
            input_dim=n_features,
            hidden_dim=self.hidden_dim,
            num_layers=self.num_layers,
            dropout=self.dropout,
            sequence_len=self.sequence_len,
            use_attention=self.use_attention
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
