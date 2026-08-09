#!/usr/bin/env bash
# Install a repository-scoped GitHub Actions runner as an isolated service.
# Run interactively with sudo; the registration token is read without echo.

set -euo pipefail
umask 0022

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNNER_USER="github-fw"
RUNNER_NAME="kalman-firmware"
RUNNER_DIR="/opt/actions-runner-plutosdr-fw"
RUNNER_HOME="${RUNNER_DIR}/home"
RUNNER_CACHE="${RUNNER_DIR}/cache"
BUILDROOT_CACHE="${RUNNER_CACHE}/buildroot-dl"
REPOSITORY_URL="https://github.com/misko/plutosdr-fw"
RUNNER_VERSION="2.336.0"
RUNNER_ARCHIVE="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
RUNNER_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_ARCHIVE}"
RUNNER_SHA256="04cf0be1aff4c3ec3554466c39124ca250e3effd8873bb7e8d68535aa9505d5d"
SERVICE_NAME="actions.runner.misko-plutosdr-fw.kalman-firmware.service"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

[[ "${EUID}" == 0 ]] || fail "run this script with sudo"
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] ||
    fail "Kalman runner requires x86-64 Linux"
[[ -r /opt/Xilinx/Vivado/2022.2/settings64.sh ]] ||
    fail "Vivado 2022.2 settings are not readable"
command -v systemctl >/dev/null || fail "systemd is required"
command -v curl >/dev/null || fail "curl is required"
command -v sha256sum >/dev/null || fail "sha256sum is required"

if id "$RUNNER_USER" >/dev/null 2>&1; then
    groups="$(id -nG "$RUNNER_USER")"
    [[ "$groups" == "$RUNNER_USER" ]] ||
        fail "$RUNNER_USER has unexpected supplementary groups: $groups"
else
    useradd --system --create-home --user-group \
        --home-dir /var/lib/github-fw --shell /usr/sbin/nologin \
        "$RUNNER_USER"
fi

install -d -m 0755 -o "$RUNNER_USER" -g "$RUNNER_USER" \
    "$RUNNER_DIR" "$RUNNER_HOME" "$RUNNER_CACHE" "$BUILDROOT_CACHE"

# Seed the persistent runner cache from an existing, already downloaded
# Buildroot tree. Do not copy transient lock files and do not replace anything
# already in the shared cache. Buildroot verifies package hashes before use.
seed_source="${REPOSITORY_ROOT}/buildroot/dl"
seeded_count=0
cached_count=0
if [[ -d "$seed_source" ]]; then
    while IFS= read -r -d '' source_file; do
        relative_path="${source_file#"${seed_source}/"}"
        target_file="${BUILDROOT_CACHE}/${relative_path}"
        target_dir="$(dirname "$target_file")"
        install -d -m 0755 -o "$RUNNER_USER" -g "$RUNNER_USER" "$target_dir"
        if [[ -e "$target_file" ]]; then
            cached_count=$((cached_count + 1))
            continue
        fi

        temporary_file="$(mktemp --tmpdir="$target_dir" .seed.XXXXXX)"
        cp --reflink=auto "$source_file" "$temporary_file"
        chown "$RUNNER_USER:$RUNNER_USER" "$temporary_file"
        chmod 0644 "$temporary_file"
        if [[ -e "$target_file" ]]; then
            rm -f "$temporary_file"
            cached_count=$((cached_count + 1))
        else
            mv "$temporary_file" "$target_file"
            seeded_count=$((seeded_count + 1))
        fi
    done < <(find "$seed_source" -type f ! -name .lock -print0)
fi
chown -R "$RUNNER_USER:$RUNNER_USER" "$BUILDROOT_CACHE"
printf 'Buildroot cache: %s (%d seeded, %d already present)\n' \
    "$BUILDROOT_CACHE" "$seeded_count" "$cached_count"

runner_configured=false
if [[ -e "$RUNNER_DIR/.runner" ]]; then
    [[ -f "$RUNNER_DIR/.runner" && -f "$RUNNER_DIR/.credentials" &&
        -f "$RUNNER_DIR/.credentials_rsaparams" ]] ||
        fail "incomplete runner registration found in $RUNNER_DIR"
    runner_configured=true
fi

if [[ -x "$RUNNER_DIR/bin/Runner.Listener" ]]; then
    installed_version="$(runuser -u "$RUNNER_USER" -- \
        env HOME="$RUNNER_HOME" bash -c \
        "cd '$RUNNER_DIR' && ./bin/Runner.Listener --version")"
    [[ "$installed_version" == "$RUNNER_VERSION" ]] ||
        fail "runner $installed_version is already unpacked; expected $RUNNER_VERSION"
    printf 'Reusing verified GitHub Actions Runner %s in %s\n' \
        "$installed_version" "$RUNNER_DIR"
else
    download_dir="$(mktemp -d /tmp/kalman-actions-runner.XXXXXX)"
    trap 'rm -rf "$download_dir"' EXIT
    curl --fail --location --proto '=https' --tlsv1.2 \
        --output "$download_dir/$RUNNER_ARCHIVE" "$RUNNER_URL"
    printf '%s  %s\n' "$RUNNER_SHA256" "$download_dir/$RUNNER_ARCHIVE" |
        sha256sum -c -
    tar -xzf "$download_dir/$RUNNER_ARCHIVE" -C "$RUNNER_DIR"
    chown -R "$RUNNER_USER:$RUNNER_USER" "$RUNNER_DIR"
fi

runuser -u "$RUNNER_USER" -- env HOME="$RUNNER_HOME" bash -c '
    source /opt/Xilinx/Vivado/2022.2/settings64.sh
    vivado -version | grep -F "Vivado v2022.2"
'

if [[ "$runner_configured" == true ]]; then
    printf 'Resuming service installation for configured runner %s\n' \
        "$RUNNER_NAME"
else
    printf 'Paste only the temporary value after --token (not the SHA or command): ' >&2
    IFS= read -r -s runner_token
    printf '\n' >&2
    runner_token="${runner_token//$'\r'/}"
    [[ -n "$runner_token" ]] || fail "registration token was empty"
    [[ "$runner_token" =~ ^[A-Za-z0-9_-]{20,50}$ ]] ||
        fail "registration token format is invalid; paste only the value after --token"

    runuser -u "$RUNNER_USER" -- env HOME="$RUNNER_HOME" bash -c \
        "cd '$RUNNER_DIR' && exec ./config.sh \"\$@\"" runner-config \
        --unattended \
        --url "$REPOSITORY_URL" \
        --token "$runner_token" \
        --name "$RUNNER_NAME" \
        --labels kalman,vivado-2022.2,plutosdr-fw \
        --work _work
    unset runner_token
fi

service_file="/etc/systemd/system/$SERVICE_NAME"
if [[ ! -e "$service_file" ]]; then
    (cd "$RUNNER_DIR" && ./svc.sh install "$RUNNER_USER")
fi
[[ -f "$service_file" ]] || fail "could not locate the installed runner service"
service_name="$SERVICE_NAME"
dropin_dir="/etc/systemd/system/${service_name}.d"
install -d -m 0755 "$dropin_dir"
cat > "$dropin_dir/hardening.conf" <<EOF
[Service]
Environment=HOME=$RUNNER_HOME
UMask=0022
NoNewPrivileges=true
PrivateDevices=true
PrivateTmp=true
ProtectClock=true
ProtectControlGroups=true
ProtectHome=true
ProtectKernelLogs=true
ProtectKernelModules=true
ProtectKernelTunables=true
ProtectProc=invisible
RestrictRealtime=true
RestrictSUIDSGID=true
CapabilityBoundingSet=
AmbientCapabilities=
EOF

systemctl daemon-reload
systemctl enable --now "$service_name"
systemctl --no-pager --full status "$service_name"

printf '\nRunner installed: %s\n' "$RUNNER_NAME"
printf 'Service: %s\n' "$service_name"
printf 'Labels: self-hosted, Linux, X64, kalman, vivado-2022.2, plutosdr-fw\n'
