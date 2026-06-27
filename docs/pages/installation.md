# Installation

Install from PyPI:

```bash
pip install shipeasy
```

Requires **Python 3.8+**. The base package has no required third-party
dependencies (only the standard library).

Import the package:

```python
import shipeasy
# or pull specific symbols:
from shipeasy import Engine, Client, configure
```

## Optional extras

The OpenFeature provider needs the `openfeature-sdk` package, shipped as an
optional extra. Install it only if you use `shipeasy.openfeature`:

```bash
pip install "shipeasy[openfeature]"
```

Importing the base `shipeasy` package never requires `openfeature-sdk`; only
importing `shipeasy.openfeature` does. See [openfeature](openfeature.md).

This is a **server** SDK: it authenticates with your **server key**
(`sdk_server_...`) and must never be embedded in a browser.
