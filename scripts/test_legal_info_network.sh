#!/bin/bash

set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
fixture=$(mktemp -d)
trap 'rm -rf "${fixture}"' EXIT

mkdir -p \
	"${fixture}/bin" \
	"${fixture}/build" \
	"${fixture}/buildroot/output/legal-info/licenses/example-1.0" \
	"${fixture}/linux" \
	"${fixture}/u-boot-xlnx/Licenses"

cp "${repo_root}/scripts/legal_info_html.sh" "${fixture}/legal_info_html.sh"
printf 'device-fw test\nlinux test\nu-boot-xlnx test\n' > "${fixture}/VERSIONS"
printf '# License\n\n# NO WARRANTY\n\nNone.\n' > "${fixture}/LICENSE.md"
printf 'Linux license\n' > "${fixture}/linux/COPYING"
printf 'U-Boot license\n' > "${fixture}/u-boot-xlnx/Licenses/gpl-2.0.txt"
printf 'Example license\n' > \
	"${fixture}/buildroot/output/legal-info/licenses/example-1.0/LICENSE"
printf '%s\n' \
	'"PACKAGE","VERSION","LICENSE","LICENSE FILES","SOURCE ARCHIVE","SOURCE SITE"' \
	'"example","1.0","MIT","LICENSE","example.tar.gz","https://sourceforge.net/projects/example/"' \
	> "${fixture}/buildroot/output/legal-info/manifest.csv"

cat > "${fixture}/bin/curl" <<'EOF'
#!/bin/bash
printf '%s\n' "$*" >> "${CURL_CALLS}"
printf 'HTTP/1.1 200 OK\r\n\r\n'
EOF
chmod +x "${fixture}/bin/curl"

export CURL_CALLS="${fixture}/curl.calls"
(
	cd "${fixture}"
	PATH="${fixture}/bin:${PATH}" ./legal_info_html.sh PlutoSDR ./VERSIONS
)
test ! -e "${CURL_CALLS}"
grep -q 'https://sourceforge.net/projects/example/' "${fixture}/build/LICENSE.html"

(
	cd "${fixture}"
	LEGAL_INFO_CHECK_URLS=1 PATH="${fixture}/bin:${PATH}" \
		./legal_info_html.sh PlutoSDR ./VERSIONS
)
test -s "${CURL_CALLS}"
grep -q -- '--connect-timeout 5 --max-time 15 --retry 0 --' "${CURL_CALLS}"

echo "legal-info network isolation: PASS"
