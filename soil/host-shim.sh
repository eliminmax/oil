#!/usr/bin/env bash
#
# Shell functions run on the host machine, OUTSIDE the container.
#
# Usage:
#   soil/host-shim.sh <function name>

set -o nounset
set -o pipefail
set -o errexit

docker-mount-perms() {
  local repo_root=$1
  local dir=$repo_root/_tmp/soil
  mkdir -p $dir
  sudo chmod --verbose 777 $dir
  ls -l -d $dir
}

run-job() {
  local docker=$1  # docker or podman
  local repo_root=$2
  local task=$3  # e.g. dev-minimal

  # docker.io is the namespace for hub.docker.com
  local image="docker.io/oilshell/soil-$task"

  local metadata_dir=$repo_root/_tmp/soil

  mkdir -p $metadata_dir  # may not exist yet

  # Use external time command in POSIX format, so it's consistent between hosts
  command time -p -o $metadata_dir/image-pull-time.txt \
    $docker pull $image

  $docker run \
      --mount "type=bind,source=$repo_root,target=/app/oil" \
      $image \
      sh -c "cd /app/oil; soil/worker.sh run-$task"
}

local-test() {
  ### Something I can run locally.  This is fast.
  local task=${1:-dummy}

  local branch=$(git rev-parse --abbrev-ref HEAD)

  local fresh_clone=/tmp/oil
  rm -r -f -v $fresh_clone

  local this_repo=$PWD
  git clone $this_repo $fresh_clone
  cd $fresh_clone
  git checkout $branch

  sudo $0 run-job docker $fresh_clone $task
}

"$@"