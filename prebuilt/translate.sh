#!/usr/bin/env bash
#
# Translate parts of Oil with mycpp, to work around circular deps issue.
#
# Usage:
#   prebuilt/translate.sh <function name>

set -o nounset
set -o pipefail
set -o errexit

REPO_ROOT=$(cd "$(dirname $0)/.."; pwd)

source mycpp/common.sh  # MYPY_REPO
source mycpp/NINJA-steps.sh

readonly TEMP_DIR=_build/tmp

oil-part() {
  ### Translate ASDL deps for unit tests

  local out_prefix=$1
  local raw_header=$2
  shift 2

  local name=asdl_runtime
  local raw=$TEMP_DIR/${name}_raw.cc 

  mkdir -p $TEMP_DIR

  local mypypath=$REPO_ROOT

  local mycpp=_bin/shwrap/mycpp_main

  ninja $mycpp
  $mycpp \
    $mypypath $raw \
    --header-out $raw_header \
    --to-header asdl.runtime \
    --to-header asdl.format \
    $REPO_ROOT/{asdl/runtime,asdl/format,core/ansi,pylib/cgi,qsn_/qsn}.py \
    "$@"

  { 
    cat <<EOF
// $out_prefix.h: GENERATED by mycpp

#include "_gen/asdl/hnode.asdl.h"
#include "cpp/qsn.h"

#include "mycpp/runtime.h"

// For hnode::External in asdl/format.py.  TODO: Remove this when that is removed.
inline Str* repr(void* obj) {
  assert(0);
}
EOF
    cat $raw_header

  } > $out_prefix.h

  { cat <<EOF
// $out_prefix.cc: GENERATED by mycpp

#include "$out_prefix.h"
EOF
    cat $raw

  } > $out_prefix.cc
}

asdl-runtime() {
  mkdir -p prebuilt/asdl $TEMP_DIR/asdl
  oil-part prebuilt/asdl/runtime.mycpp $TEMP_DIR/asdl/runtime_raw.mycpp.h
}

frontend-args() {
  mkdir -p prebuilt/frontend $TEMP_DIR/frontend
  oil-part prebuilt/frontend/args.mycpp $TEMP_DIR/frontend/args_raw.mycpp.h \
    --to-header frontend.args \
    frontend/args.py 
}

"$@"
