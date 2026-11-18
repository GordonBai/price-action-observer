#!/bin/sh
# Launch from this checkout without embedding a user's computer path.
cd -- "$(dirname -- "$0")" || exit 1
if [ -n "${PA_OBSERVER_PYTHON:-}" ]; then
    PYTHON="$PA_OBSERVER_PYTHON"
elif [ -x .venv/bin/python ]; then
    PYTHON=.venv/bin/python
elif [ -x ../robinhood-trading-infra/.venv/bin/python ]; then
    PYTHON=../robinhood-trading-infra/.venv/bin/python
else
    PYTHON=$(command -v python3) || { printf '%s\n' 'Install Python and project requirements first; see README.'; exit 1; }
fi
exec "$PYTHON" -m pa_lens wizard
