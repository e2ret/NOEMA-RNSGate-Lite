#!/bin/bash
# MeshGate install script
# Supports: Debian / Ubuntu / Armbian

set -e

REPO_URL="https://github.com/e2ret/NOEMA-RNSGate-Lite.git"
INSTALL_DIR="$HOME/NOEMA-RNSGate-Lite"
RNS_CONFIG_DIR="$HOME/.reticulum"
LXMF_TOOLS_DIR="$HOME/lxmf-tools"
PYTHON="$INSTALL_DIR/.venv/bin/python3"
CURRENT_USER="${SUDO_USER:-$USER}"
[ "$EUID" -eq 0 ] && CURRENT_USER=root
CURRENT_HOME=$(eval echo "~$CURRENT_USER")

echo "========================================"
echo "  NOEMA RNSGate Installer"
echo "========================================"
echo ""

# --- Check root ---
if [ "$EUID" -ne 0 ]; then
    echo "[ERROR] Please run as root: sudo bash install.sh"
    exit 1
fi

# --- System dependencies ---
echo "[1/7] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    gcc \
    python3-dev \
    libffi-dev \
    python3-cffi \
    python3-cryptography

# --- Clone or update MeshGate ---
echo "[2/7] Getting MeshGate..."
if [ -d "$INSTALL_DIR" ]; then
    echo "      Directory $INSTALL_DIR already exists, pulling latest..."
    git -C "$INSTALL_DIR" pull
else
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# --- Install i2pd from bundled package ---
echo "[2b] Installing i2pd..."
ARCH=$(uname -m)
if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    I2PD_DEB="$INSTALL_DIR/packages/i2pd_2.60.0-1forky1_arm64.deb"
elif [ "$ARCH" = "armv7l" ] || [ "$ARCH" = "armhf" ]; then
    I2PD_DEB="$INSTALL_DIR/packages/i2pd_2.60.0-1forky1_armhf.deb"
else
    I2PD_DEB="$INSTALL_DIR/packages/i2pd_2.60.0-1forky1_amd64.deb"
fi

if [ -f "$I2PD_DEB" ]; then
    if sudo dpkg -i "$I2PD_DEB" 2>/dev/null; then
        echo "      i2pd installed from bundle."
    else
        echo "      [INFO] Bundle install failed, trying apt-get install -f..."
        sudo apt-get install -f -y 2>/dev/null || true
    fi
    # Try apt install as fallback
    if ! systemctl list-unit-files i2pd.service &>/dev/null; then
        echo "      [INFO] i2pd service not found, trying apt..."
        sudo apt-get install -y i2pd 2>/dev/null || true
    fi
    if systemctl list-unit-files i2pd.service &>/dev/null; then
        sudo systemctl enable --now i2pd
        echo "      i2pd service enabled."
    else
        echo "      [WARN] i2pd service not available, skipping."
    fi
else
    echo "      [INFO] Bundled i2pd not found, trying apt..."
    sudo apt-get install -y i2pd 2>/dev/null || echo "      [WARN] i2pd not available via apt."
    if systemctl list-unit-files i2pd.service &>/dev/null; then
        sudo systemctl enable --now i2pd
        echo "      i2pd installed from apt."
    fi
fi

# --- Copy logo to dashboard ---
if [ -f "$INSTALL_DIR/docs/logo.png" ] && [ ! -f "$INSTALL_DIR/dashboard/logo.png" ]; then
    cp "$INSTALL_DIR/docs/logo.png" "$INSTALL_DIR/dashboard/logo.png"
    echo "      Logo copied to dashboard."
fi

# --- Python venv ---
echo "[3/7] Setting up Python virtual environment..."
python3 -m venv --system-site-packages "$INSTALL_DIR/.venv"
source "$INSTALL_DIR/.venv/bin/activate"

pip install --upgrade pip -q
pip install \
    rns \
    lxmf \
    lxmfy \
    flask \
    paho-mqtt \
    nomadnet \
    pytz \
    requests \
    geopy

echo "      Python dependencies installed."

# --- Reticulum config ---
echo "[4/7] Setting up Reticulum config..."
mkdir -p "$RNS_CONFIG_DIR"

if [ -f "$RNS_CONFIG_DIR/config" ]; then
    echo "      Reticulum config already exists, skipping."
else
    cat > "$RNS_CONFIG_DIR/config" << 'RNSEOF'
[reticulum]
  enable_transport = Yes
  share_instance = Yes
  shared_instance_port = 37428
  instance_control_port = 37429
  panic_on_interface_error = No

[interfaces]

  [[Default Interface]]
    type = AutoInterface
    enabled = yes

  [[TCP]]
    type = TCPServerInterface
    enabled = true
    port = 4242
    listen_ip = 0.0.0.0
RNSEOF
    echo "      Default Reticulum config created."
fi

# --- MQTT configuration ---
echo ""
echo "========================================"
echo "  MQTT Broker Configuration"
echo "========================================"
echo ""
read -rp "  MQTT broker IP [localhost]: " MQTT_HOST
MQTT_HOST="${MQTT_HOST:-localhost}"
read -rp "  MQTT port [1883]: " MQTT_PORT
MQTT_PORT="${MQTT_PORT:-1883}"
read -rp "  MQTT username [mqtt]: " MQTT_USER
MQTT_USER="${MQTT_USER:-mqtt}"
read -rsp "  MQTT password: " MQTT_PASS
echo ""
echo "      MQTT: $MQTT_USER@$MQTT_HOST:$MQTT_PORT"
echo ""

# --- lxmf-tools ---
echo "[5/7] Setting up lxmf-tools..."
mkdir -p "$LXMF_TOOLS_DIR"
cp "$INSTALL_DIR/lxmf-tools/noema_lxmf_bridge.py" "$LXMF_TOOLS_DIR/noema_lxmf_bridge.py"


if [ -f "$LXMF_TOOLS_DIR/config.cfg.owr" ]; then
    echo "      lxmf-tools config already exists, skipping."
else
    cat > "$LXMF_TOOLS_DIR/config.cfg.owr" << EOF
[main]
enabled = True
power = Yes

[lxmf]
destination_name = lxmf
destination_type = delivery
display_name = LXMF Bridge
announce_startup = Yes
announce_startup_delay = 0
signature_validated = No

[mqtt]
host = ${MQTT_HOST}
port = ${MQTT_PORT}
transport = tcp
client_id = lxmf_mqtt_bridge
username = ${MQTT_USER}
password = ${MQTT_PASS}

[router]
lxmf_to_mqtt = True
mqtt_to_lxmf = True
lxmf_announce_to_mqtt = False
state_to_mqtt = True

[topics]
topic_send = message/lxmf/send
topic_receive = message/lxmf/receive
topic_announce = message/lxmf/announce
topic_power = message/lxmf/power
topic_state = message/lxmf/state
topic_rm_power = message/lxmf/rm_power
topic_rm_state = message/lxmf/rm_state
state_interval = 60
state_startup = Yes
state_periodic = Yes
EOF
    echo "      Created lxmf-tools config."
fi



# --- Serial port access for RNode ---
if groups "$CURRENT_USER" | grep -qw dialout; then
    echo "      User $CURRENT_USER already in dialout group."
else
    sudo usermod -aG dialout "$CURRENT_USER"
    echo "      Added $CURRENT_USER to dialout group."
    echo "      [!] You need to log out and back in for serial port access."
fi

# --- Systemd services ---
echo "[6/7] Installing systemd services..."

install_service() {
    local NAME=$1
    local DESC=$2
    local EXEC=$3
    local WORKDIR=$4
    local AFTER=${5:-"network.target"}

    sudo tee "/etc/systemd/system/${NAME}.service" > /dev/null << EOF
[Unit]
Description=${DESC}
After=${AFTER}

[Service]
User=${CURRENT_USER}
WorkingDirectory=${WORKDIR}
Environment=HOME=${CURRENT_HOME}
ExecStart=${EXEC}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    echo "      Installed ${NAME}.service"
}

install_service "rnsd" \
    "Reticulum Network Stack Daemon" \
    "$INSTALL_DIR/.venv/bin/rnsd --config $RNS_CONFIG_DIR" \
    "$INSTALL_DIR"

install_service "noema_lxmf_bridge" \
    "NOEMA LXMF Bridge" \
    "$PYTHON $LXMF_TOOLS_DIR/noema_lxmf_bridge.py" \
    "$LXMF_TOOLS_DIR" \
    "network.target rnsd.service"

install_service "dashboard" \
    "NOEMA RNSGate Dashboard" \
    "$PYTHON $INSTALL_DIR/dashboard/app.py" \
    "$INSTALL_DIR/dashboard" \
    "network.target"

SERVICES_LIST="rnsd noema_lxmf_bridge dashboard"

# --- Nomadnet node ---
echo "[7b] Setting up Nomadnet node..."
NOMADNET_PAGES="$CURRENT_HOME/.nomadnetwork/storage/pages"
mkdir -p "$NOMADNET_PAGES"

if [ ! -f "$NOMADNET_PAGES/index.mu" ]; then
    cat > "$NOMADNET_PAGES/index.mu" << 'MUEOF'
> NOEMA RNSGate

`c`fNOEMA RNSGate`f

`c`bReticulum Mesh Gateway`b

---

`c`[Подключение`]

TCP: <IP>:4242

---

`c`[Контакт`]

LXMF Bridge: <адрес из дашборда>
Group Chat:  <адрес из дашборда>

---

`c`aNOEMA — передавай смысл, а не просто данные`a
MUEOF
    echo "      Default index.mu created."
fi

# --- Nomadnet ChatRoom ---
echo "[7c] Setting up Nomadnet ChatRoom..."
cd /tmp && git clone https://github.com/fr33n0w/thechatroom.git thechatroom_install 2>/dev/null || true
if [ -d "/tmp/thechatroom_install" ]; then
    cp /tmp/thechatroom_install/nomadnet.mu "$NOMADNET_PAGES/"
    cp /tmp/thechatroom_install/meshchat.mu "$NOMADNET_PAGES/"
    cp /tmp/thechatroom_install/fullchat.mu "$NOMADNET_PAGES/"
    cp /tmp/thechatroom_install/last100.mu  "$NOMADNET_PAGES/"
    cp /tmp/thechatroom_install/chat_log.json "$NOMADNET_PAGES/"
    cp /tmp/thechatroom_install/topic.json "$NOMADNET_PAGES/"
    cp /tmp/thechatroom_install/emoticon.txt "$NOMADNET_PAGES/"
    chmod +x "$NOMADNET_PAGES/nomadnet.mu" "$NOMADNET_PAGES/meshchat.mu" \
              "$NOMADNET_PAGES/fullchat.mu" "$NOMADNET_PAGES/last100.mu"
    # Fix emoticon filename
    ln -sf "$NOMADNET_PAGES/emoticon.txt" "$NOMADNET_PAGES/emoticons.txt"
    rm -rf /tmp/thechatroom_install
    echo "      ChatRoom installed."
else
    echo "      [WARN] Could not clone thechatroom, skipping."
fi
cd "$INSTALL_DIR"

# Enable nomadnet node in config — init first run to create config
NOMADNET_CONFIG="$CURRENT_HOME/.nomadnetwork/config"
if [ ! -f "$NOMADNET_CONFIG" ]; then
    echo "      Initializing Nomadnet config..."
    timeout 5 "$INSTALL_DIR/.venv/bin/nomadnet" --daemon --rnsconfig "$RNS_CONFIG_DIR" 2>/dev/null || true
    sleep 2
fi
if [ -f "$NOMADNET_CONFIG" ]; then
    sed -i "s/^enable_node = no/enable_node = yes/" "$NOMADNET_CONFIG"
    sed -i "s/^node_name = None/node_name = NOEMA RNSGate/" "$NOMADNET_CONFIG"
    echo "      Nomadnet node enabled in config."
fi

install_service "nomadnet" \
    "Nomadnet Node" \
    "$INSTALL_DIR/.venv/bin/nomadnet --daemon --rnsconfig $RNS_CONFIG_DIR" \
    "$CURRENT_HOME" \
    "network.target rnsd.service"

SERVICES_LIST="$SERVICES_LIST nomadnet"

sudo systemctl daemon-reload
sudo systemctl enable $SERVICES_LIST
echo "      Services enabled."
echo "      Starting services..."
sudo systemctl start $SERVICES_LIST

# --- Done ---
echo ""
echo "========================================"
echo "  Installation complete!"
echo "========================================"
echo ""
echo "  NOEMA RNSGate directory : $INSTALL_DIR"
echo "  lxmf-tools         : $LXMF_TOOLS_DIR"
echo "  Reticulum config   : $RNS_CONFIG_DIR/config"
echo "  Python venv        : $INSTALL_DIR/.venv"
echo "  Dashboard          : http://$(hostname -I | awk '{print $1}'):8081"
echo ""
echo "  Edit Reticulum config:"
echo "    nano $RNS_CONFIG_DIR/config"
echo ""
echo "  Check status:"
echo "    sudo systemctl status $SERVICES_LIST"
echo ""

# --- Install rBrowser ---
echo "Installing rBrowser..."
if [ ! -d "/root/rBrowser" ]; then
    git clone https://github.com/fr33n0w/rBrowser.git /root/rBrowser
    "$INSTALL_DIR/.venv/bin/pip" install waitress --quiet
    echo "  [OK] rBrowser cloned"
else
    echo "  [SKIP] rBrowser already installed"
fi

if [ ! -f /etc/systemd/system/rbrowser.service ]; then
cat > /etc/systemd/system/rbrowser.service << SVCEOF
[Unit]
Description=rBrowser Nomadnet Browser
After=network.target rnsd.service
Wants=rnsd.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/rBrowser
ExecStart=$INSTALL_DIR/.venv/bin/python3 rBrowser.py
Restart=on-failure
RestartSec=5
TimeoutStartSec=30

[Install]
WantedBy=multi-user.target
SVCEOF
    systemctl daemon-reload
    systemctl enable rbrowser
    echo "  [OK] rbrowser.service installed"
fi

# --- Calculate Nomadnet node address ---
echo "Calculating Nomadnet node address..."
sleep 10
"$INSTALL_DIR/.venv/bin/python3" "$INSTALL_DIR/recalc_nn_addr.py" || true
