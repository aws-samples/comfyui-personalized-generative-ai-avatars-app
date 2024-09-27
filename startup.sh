#!/bin/bash
set -e
echo "Starting startup.sh script..."
EFS_MOUNT="/home/user/opt/ComfyUI"
VENV_PATH="$EFS_MOUNT/.venv"

# Use the system Python 3.10
PYTHON_BIN="/usr/bin/python3"

if [ ! -f "$EFS_MOUNT/main.py" ]; then
    echo "main.py not found in EFS mount. Copying files..."
    mkdir -p "$EFS_MOUNT"
    cp -rn /app/ComfyUI/. "$EFS_MOUNT/" || { echo "Failed to copy files to EFS"; exit 1; }
else
    echo "main.py found in EFS mount. Skipping copy."
fi

echo "Setting up virtual environment"
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating virtual environment with system packages..."
    $PYTHON_BIN -m venv $VENV_PATH --system-site-packages || { echo "Failed to create virtual environment"; exit 1; }
fi

# Activate virtual environment
source "$VENV_PATH/bin/activate" || { echo "Failed to activate virtual environment"; exit 1; }

echo "Python interpreter used: $(which python)"
echo "Python version: $(python --version)"
echo "Pip used: $(which pip)"
echo "Virtual environment: $VIRTUAL_ENV"

# Install only missing requirements
if [ ! -f "$EFS_MOUNT/.requirements_installed" ]; then
    echo "Installing missing requirements..."
    pip install --no-deps -r $EFS_MOUNT/requirements.txt
    touch "$EFS_MOUNT/.requirements_installed"
else
    echo "Requirements already installed. Skipping."
fi

echo "Starting ComfyUI..."
exec python "$EFS_MOUNT/main.py" --listen 0.0.0.0 --port 8181 --output-directory "$EFS_MOUNT/output/"