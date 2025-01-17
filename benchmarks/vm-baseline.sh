#!/usr/bin/env bash
#
# Do a quick test of virtual memory.
# TODO: We could use Max RSS instead?  Didn't know about that when I originally
# wrote this.
#
# Usage:
#   benchmarks/vm-baseline.sh <function name>

set -o nounset
set -o pipefail
set -o errexit

source test/common.sh  # log
source benchmarks/common.sh

readonly BASE_DIR=_tmp/vm-baseline

measure() {
  local provenance=$1
  local base_dir=${2:-_tmp/vm-baseline}

  local name=$(basename $provenance)
  local prefix=${name%.provenance.txt}  # strip suffix

  local out_dir="$base_dir/$prefix"
  mkdir -p $out_dir

  # Fourth column is the shell.
  # TODO: when oil-native can start processes, hook it up!
  cat $provenance | filter-provenance "${SHELLS[@]}" $OIL_NATIVE_REGEX |
  while read _ _ _ sh_path shell_hash; do
    # _bin/cxx-opt/osh_eval.stripped -> osh_eval.stripped
    # TODO: bumpleak
    local sh_name=$(basename $sh_path)
    local out="$out_dir/${sh_name}-${shell_hash}.txt"

    # There is a race condition on the status but sleep helps.
    # Bug fix: ALIVE to prevent exec optimization in OSH and zsh.
    $sh_path -c 'sleep 0.001; cat /proc/$$/status; echo ALIVE' > $out
  done

  echo
  echo "$out_dir:"
  ls -l $out_dir
}

# Run a single file through stage 1 and report.
demo() {
  local -a job_dirs=($BASE_DIR/lisa.2017-*)
  local dir1=$BASE_DIR/stage1
  local dir2=$BASE_DIR/stage2

  mkdir -p $dir1 $dir2
  
  benchmarks/virtual_memory.py baseline ${job_dirs[-1]} \
    > $dir1/vm-baseline.csv

  benchmarks/report.R vm-baseline $dir1 $dir2
}

# Combine CSV files.
stage1() {
  local raw_dir=${1:-$BASE_DIR/raw}
  local single_machine=${2:-}

  local out=$BASE_DIR/stage1
  mkdir -p $out

  local base_dir=

  local -a raw=()

  if test -n "$single_machine"; then
    base_dir=_tmp/vm-baseline
    local -a m1=( $base_dir/$single_machine.* )
    raw+=( ${m1[-1]} )
  else
    base_dir=../benchmark-data/vm-baseline
    # Globs are in lexicographical order, which works for our dates.
    local -a m1=( $base_dir/$MACHINE1.* )
    local -a m2=( $base_dir/$MACHINE2.* )

    raw+=( ${m1[-1]} ${m2[-1]} )
  fi

  benchmarks/virtual_memory.py baseline "${raw[@]}" \
    | tee $out/vm-baseline.csv
}

print-report() {
  local in_dir=$1

  benchmark-html-head 'Virtual Memory Baseline'

  cat <<EOF
  <body class="width60">
    <p id="home-link">
      <a href="/">oilshell.org</a>
    </p>
EOF

  cmark << 'EOF'
## Virtual Memory Baseline

Source code: [oil/benchmarks/vm-baseline.sh](https://github.com/oilshell/oil/tree/master/benchmarks/vm-baseline.sh)

### Memory Used at Startup (MB)

Memory usage is measured in MB (powers of 10), not MiB (powers of 2).

EOF
  csv2html $in_dir/vm-baseline.csv

  # R code doesn't generate this
  if false; then
    cmark <<< '### Shell and Host Details'

    csv2html $in_dir/shells.csv
    csv2html $in_dir/hosts.csv
  fi

  cat <<EOF
  </body>
</html>
EOF
}


#
# Other
#

soil-shell-provenance() {
  ### Only measure shells in the Docker image

  local label=$1
  shift

  # TODO: mksh, zsh
  benchmarks/id.sh shell-provenance "$label" bash dash bin/osh "$@"
}

soil-run() {
  ### Run it on just this machine, and make a report

  rm -r -f $BASE_DIR
  mkdir -p $BASE_DIR

  # TODO: could add _bin/cxx-bumpleak/osh_eval, but we would need to fix
  # $shell_name 
  local -a oil_bin=(_bin/cxx-opt/osh_eval.stripped)
  ninja "${oil_bin[@]}"

  local label='no-host'

  local provenance
  provenance=$(soil-shell-provenance $label "${oil_bin[@]}")

  measure $provenance

  # Make it run on one machine
  stage1 '' $label

  benchmarks/report.sh stage2 $BASE_DIR
  benchmarks/report.sh stage3 $BASE_DIR
}

"$@"
