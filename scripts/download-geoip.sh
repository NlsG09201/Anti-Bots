#!/bin/bash
# Descarga GeoLite2-City usando license key de MaxMind
set -euo pipefail

: "${MAXMIND_LICENSE_KEY:?Set MAXMIND_LICENSE_KEY}"

mkdir -p backend/data
TMP=$(mktemp -d)
curl -sSL "https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key=${MAXMIND_LICENSE_KEY}&suffix=tar.gz" -o "$TMP/geoip.tar.gz"
tar -xzf "$TMP/geoip.tar.gz" -C "$TMP"
find "$TMP" -name 'GeoLite2-City.mmdb' -exec cp {} backend/data/GeoLite2-City.mmdb \;
echo "GeoIP database saved to backend/data/GeoLite2-City.mmdb"
rm -rf "$TMP"
