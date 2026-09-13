#!/bin/sh
# Preserve the public SSH entry point and its status for all callers.
exec /usr/sbin/pluto-fw-update "$@"
