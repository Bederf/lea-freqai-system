# GitHub Issue for FreqTrade Repository

**Title:** Custom PyTorch models in user_data/freqaimodels fail to pickle/save

**Labels:** `freqai`, `bug`, `pytorch`

---

## Description

Custom PyTorch models placed in `user_data/freqaimodels/` fail to save after training with a `PicklingError`. This makes it impossible to use custom LSTM, GRU, or other custom PyTorch architectures with FreqAI.

## Error

```python
PicklingError: Can't pickle <class 'LeaTorchLSTM.SimpleLSTMModel'>: import of module 'LeaTorchLSTM' failed
```

## Steps to Reproduce

1. Create custom PyTorch model in `user_data/freqaimodels/MyModel.py`:

```python
import torch.nn as nn
from freqtrade.freqai.base_models.BasePyTorchRegressor import BasePyTorchRegressor

class CustomLSTM(nn.Module):
    def __init__(self, input_dim, hidden_dim=128):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True)
        self.fc = nn.Linear(hidden_dim, 1)

    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        return self.fc(lstm_out[:, -1, :])

class MyModel(BasePyTorchRegressor):
    def fit(self, data_dictionary, dk, **kwargs):
        model = CustomLSTM(input_dim=100)  # Custom model
        trainer = PyTorchModelTrainer(model=model, ...)
        trainer.fit(data_dictionary, self.splits)
        return trainer  # ❌ Pickling fails here
```

2. Run training:
```bash
freqtrade trade --freqaimodel MyModel
```

3. Observe error in logs:
```
ERROR - Training BTC/USDT raised exception PicklingError. Message: Can't pickle <class 'MyModel.CustomLSTM'>: import of module 'MyModel' failed, skipping.
```

## Root Cause

When FreqTrade saves the `PyTorchModelTrainer` object (which contains the model), Python's pickle mechanism needs to be able to re-import the model class. However:

1. Custom models are in `user_data/freqaimodels/`
2. This path is not in Python's import path during unpickling
3. Pickle tries: `from MyModel import CustomLSTM` and fails

Built-in models work because they're in proper packages:
- ✅ `freqtrade.freqai.torch.PyTorchMLPModel`
- ✅ `freqtrade.freqai.torch.PyTorchTransformerModel`
- ❌ `user_data.freqaimodels.MyModel` (not importable)

## Expected Behavior

Custom PyTorch models in `user_data/freqaimodels/` should save and load successfully, just like built-in models.

## Current Workaround

Use built-in models only:
- `PyTorchMLPRegressor`
- `PyTorchTransformerRegressor`

## Proposed Solutions

### Option 1: Fix Import Path
Add `user_data/freqaimodels` to Python's import path before unpickling:

```python
# In BasePyTorchModel or wherever unpickling happens
import sys
user_models_path = Path("user_data/freqaimodels")
if user_models_path not in sys.path:
    sys.path.insert(0, str(user_models_path))
```

### Option 2: Use state_dict Instead of Pickling
Save only model weights, not entire trainer object:

```python
def save_model(self, path):
    torch.save({
        'model_state_dict': self.model.state_dict(),
        'optimizer_state_dict': self.optimizer.state_dict(),
        'config': self.config
    }, path)

def load_model(self, path):
    checkpoint = torch.load(path)
    self.model.load_state_dict(checkpoint['model_state_dict'])
    self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
```

This is more standard PyTorch practice and avoids pickling issues entirely.

### Option 3: Documentation
At minimum, document this limitation clearly in the FreqAI docs with guidance on:
- Which models can be customized
- How to contribute models to FreqTrade source if needed
- Best practices for model development

## Environment

- **FreqTrade version:** 2025.9
- **Python version:** 3.13
- **OS:** Linux (Ubuntu/Debian)
- **Installation:** Git clone

## Additional Context

This affects anyone trying to use custom LSTM, GRU, Transformer variants, or any custom PyTorch architecture with FreqAI. The only current solution is to modify FreqTrade source code directly, which is not maintainable.

Built-in `PyTorchMLPRegressor` works fine as a workaround, but limits architectural experimentation for advanced users.

## Related

- Similar issue might affect custom TensorFlow/Keras models if they exist
- Documentation: https://www.freqtrade.io/en/stable/freqai/
