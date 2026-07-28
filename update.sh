#!/bin/bash
set -e

INSTALL_DIR="/root/NOEMA-RNSGate"
VENV="$INSTALL_DIR/.venv/bin/python3"
PIP="$INSTALL_DIR/.venv/bin/pip"

echo "=== NOEMA RNSGate Update ==="

# Copy dashboard files
echo "Updating dashboard..."
cp "$INSTALL_DIR/dashboard/app.py" "$INSTALL_DIR/dashboard/app.py.bak" 2>/dev/null || true
cp "$INSTALL_DIR/dashboard/index.html" "$INSTALL_DIR/dashboard/index.html.bak" 2>/dev/null || true

# Install rBrowser if missing
if [ ! -d "/root/rBrowser" ]; then
    echo "Installing rBrowser..."
    git clone https://github.com/fr33n0w/rBrowser.git /root/rBrowser
    $PIP install waitress --quiet
    echo "  [OK] rBrowser installed"
else
    echo "  [SKIP] rBrowser already exists"
fi

# Install rbrowser.service if missing
if [ ! -f /etc/systemd/system/rbrowser.service ]; then
    echo "Installing rbrowser.service..."
    cat > /etc/systemd/system/rbrowser.service << SVCEOF
[Unit]
Description=rBrowser Nomadnet Browser
After=network.target rnsd.service
Wants=rnsd.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/rBrowser
ExecStart=${INSTALL_DIR}/.venv/bin/python3 rBrowser.py
Restart=on-failure
RestartSec=5
TimeoutStartSec=30

[Install]
WantedBy=multi-user.target
SVCEOF
    systemctl daemon-reload
    systemctl enable rbrowser
    echo "  [OK] rbrowser.service installed"
else
    echo "  [SKIP] rbrowser.service already exists"
fi

# Restart all services
echo "Restarting services..."
systemctl restart dashboard lxmf_bridge_mqtt lxmf_group_chat nomadnet rbrowser rnsd
sleep 3

# Status
echo ""
echo "=== Service Status ==="
for s in rnsd dashboard lxmf_bridge_mqtt lxmf_group_chat nomadnet rbrowser; do
    status=$(systemctl is-active $s 2>/dev/null)
    echo "  $s: $status"
done

echo ""
echo "=== Update complete ==="
