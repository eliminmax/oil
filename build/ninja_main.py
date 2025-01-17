#!/usr/bin/env python2
"""
build/ninja_main.py - invoked by ./NINJA-config.sh

See build/README.md for the code and data layout.

"""
from __future__ import print_function

import cStringIO
from glob import glob
import os
import sys

from build import ninja_lib
from build.ninja_lib import log

from asdl import NINJA_subgraph as asdl_subgraph
from bin import NINJA_subgraph as bin_subgraph
from core import NINJA_subgraph as core_subgraph
from cpp import NINJA_subgraph as cpp_subgraph
from frontend import NINJA_subgraph as frontend_subgraph
from oil_lang import NINJA_subgraph as oil_lang_subgraph
from osh import NINJA_subgraph as osh_subgraph
from mycpp import NINJA_subgraph as mycpp_subgraph
from pea import NINJA_subgraph as pea_subgraph
from prebuilt import NINJA_subgraph as prebuilt_subgraph

from vendor import ninja_syntax


# The file Ninja runs by default.
BUILD_NINJA = 'build.ninja'


def TarballManifest(cc_sources):
  names = []

  # Text
  names.extend([
    'LICENSE.txt',
    'README-native.txt',
    ])

  # Code we know about
  names.extend(cc_sources)

  names.extend(glob('mycpp/*.h'))

  # TODO: crawl headers
  names.extend(glob('cpp/*.h'))

  # TODO: Put these in Ninja.
  names.extend(glob('_gen/asdl/*.h'))
  names.extend(glob('_gen/frontend/*.h'))
  names.extend(glob('_gen/core/*.h'))
  names.extend(glob('_gen/oil_lang/*.h'))

  # ONLY the headers
  names.extend(glob('prebuilt/*/*.h'))

  # Build scripts
  names.extend([
    'build/common.sh',
    'build/native.sh',
    'build/ninja-rules-cpp.sh',
    'mycpp/common.sh',

    # Generated
    '_build/oil-native.sh',
    ])

  for name in names:
    print(name)


def ShellFunctions(cc_sources, f, argv0):
  """
  Generate a shell script that invokes the same function that build.ninja does
  """
  print('''\
#!/usr/bin/env bash
#
# _build/oil-native.sh - generated by %s
#
# Usage
#   _build/oil-native COMPILER? VARIANT? SKIP_REBUILD?
#
#   COMPILER: 'cxx' for system compiler, or 'clang' [default cxx]
#   VARIANT: 'dbg' or 'opt' [default dbg]
#   SKIP_REBUILD: if non-empty, checks if the output exists before building
#
# Could run with /bin/sh, but use bash for now, bceause dash has bad errors messages!
#!/bin/sh

. build/ninja-rules-cpp.sh

main() {
  ### Compile oil-native into _bin/$compiler-$variant-sh/ (not with ninja)

  local compiler=${1:-cxx}   # default is system compiler
  local variant=${2:-opt}    # default is optimized build
  local skip_rebuild=${3:-}  # if the output exists, skip build'

''' % (argv0), file=f)

  out = '_bin/$compiler-$variant-sh/osh_eval'
  print('  local out=%s' % out, file=f)

  print('''\
  if test -n "$skip_rebuild" && test -f "$out"; then
    echo
    echo "$0: SKIPPING build because $out exists"
    echo
    return
  fi

  echo
  echo "$0: Building oil-native: $out"
  echo

  mkdir -p "_build/obj/$compiler-$variant-sh" "_bin/$compiler-$variant-sh"
''', file=f)

  objects = []
  for src in cc_sources:
    # e.g. _build/obj/dbg/posix.o
    base_name, _ = os.path.splitext(os.path.basename(src))

    obj_quoted = '"_build/obj/$compiler-$variant-sh/%s.o"' % base_name
    objects.append(obj_quoted)

    print("  echo 'CXX %s'" % src, file=f)
    print('  compile_one "$compiler" "$variant" "" \\', file=f)
    print('    %s %s' % (src, obj_quoted), file=f)

  print('', file=f)

  print('  echo "LINK $out"', file=f)
  # note: can't have spaces in filenames
  print('  link "$compiler" "$variant" "$out" \\', file=f)
  # put each object on its own line, and indent by 4
  print('    %s' % (' \\\n    '.join(objects)), file=f)
  print('', file=f)

  # Strip opt binary
  # TODO: provide a way for the user to get symbols?

  print('''\
  if test "$variant" = opt; then
    strip -o "$out.stripped" "$out"
  fi
}

main "$@"
''', file=f)


def Preprocessed(n, cc_sources):
  # See how much input we're feeding to the compiler.  Test C++ template
  # explosion, e.g. <unordered_map>
  #
  # Limit to {dbg,opt} so we don't generate useless rules.  Invoked by
  # metrics/source-code.sh

  pre_matrix = [
      ('cxx', 'dbg'),
      ('cxx', 'opt'),
      ('clang', 'dbg'),
      ('clang', 'opt'),
  ]
  for compiler, variant in pre_matrix:
    preprocessed = []
    for src in cc_sources:
      # e.g. _build/preprocessed/cxx-dbg/mycpp/gc_heap.cc
      rel_path, _ = os.path.splitext(src)
      pre = '_build/preprocessed/%s-%s/%s.cc' % (compiler, variant, rel_path)
      preprocessed.append(pre)

    # Summary file
    n.build('_build/preprocessed/%s-%s.txt' % (compiler, variant),
            'line_count',
            preprocessed)
    n.newline()


def InitSteps(n):
  """Wrappers for build/ninja-rules-*.sh

  Some of these are defined in mycpp/NINJA_subgraph.py.  Could move them here.
  """

  #
  # Compiling and linking
  #

  # Preprocess one translation unit
  n.rule('preprocess',
         # compile_one detects the _build/preprocessed path
         command='build/ninja-rules-cpp.sh compile_one $compiler $variant $more_cxx_flags $in $out',
         description='PP $compiler $variant $more_cxx_flags $in $out')
  n.newline()

  n.rule('line_count',
         command='build/ninja-rules-cpp.sh line_count $out $in',
         description='line_count $out $in')
  n.newline()

  # Compile one translation unit
  n.rule('compile_one',
         command='build/ninja-rules-cpp.sh compile_one $compiler $variant $more_cxx_flags $in $out $out.d',
         depfile='$out.d',
         # no prefix since the compiler is the first arg
         description='$compiler $variant $more_cxx_flags $in $out')
  n.newline()

  # Link objects together
  n.rule('link',
         command='build/ninja-rules-cpp.sh link $compiler $variant $out $in',
         description='LINK $compiler $variant $out $in')
  n.newline()

  # 1 input and 2 outputs
  n.rule('strip',
         command='build/ninja-rules-cpp.sh strip_ $in $out',
         description='STRIP $in $out')
  n.newline()

  #
  # Code generators
  #

  n.rule('write-shwrap',
         # $in must start with main program
         command='build/ninja-rules-py.sh write-shwrap $template $out $in',
         description='make-pystub $out $in')
  n.newline()

  n.rule('gen-osh-eval',
         command='build/ninja-rules-py.sh gen-osh-eval $out_prefix $in',
         description='gen-osh-eval $out_prefix $in')
  n.newline()


def main(argv):
  try:
    action = argv[1]
  except IndexError:
    action = 'ninja'

  if action == 'ninja':
    f = open(BUILD_NINJA, 'w')
  else:
    f = cStringIO.StringIO()  # thrown away

  n = ninja_syntax.Writer(f)
  ru = ninja_lib.Rules(n)

  ru.comment('InitSteps()')
  InitSteps(n)

  #
  # Create the graph.
  #

  asdl_subgraph.NinjaGraph(ru)
  ru.comment('')

  bin_subgraph.NinjaGraph(ru)
  ru.comment('')

  core_subgraph.NinjaGraph(ru)
  ru.comment('')

  cpp_subgraph.NinjaGraph(ru)
  ru.comment('')

  frontend_subgraph.NinjaGraph(ru)
  ru.comment('')

  mycpp_subgraph.NinjaGraph(ru)
  ru.comment('')

  oil_lang_subgraph.NinjaGraph(ru)
  ru.comment('')

  osh_subgraph.NinjaGraph(ru)
  ru.comment('')

  pea_subgraph.NinjaGraph(ru)
  ru.comment('')

  prebuilt_subgraph.NinjaGraph(ru)
  ru.comment('')


  # Materialize all the cc_binary() rules
  ru.WriteRules()

  # Collect sources for metrics, tarball, shell script
  cc_sources = ru.SourcesForBinary('_gen/bin/osh_eval.mycpp.cc')

  if 0:
    from pprint import pprint
    pprint(cc_sources)

  # TODO: could thin these out, not generate for unit tests, etc.
  Preprocessed(n, cc_sources)

  ru.WritePhony()

  n.default(['_bin/cxx-dbg/osh_eval'])


  if action == 'ninja':
    log('  (%s) -> %s (%d targets)', argv[0], BUILD_NINJA,
        n.num_build_targets())

  elif action == 'shell':
    out = '_build/oil-native.sh'
    with open(out, 'w') as f:
      ShellFunctions(cc_sources, f, argv[0])
    log('  (%s) -> %s', argv[0], out)

  elif action == 'tarball-manifest':
    TarballManifest(cc_sources)

  else:
    raise RuntimeError('Invalid action %r' % action)


if __name__ == '__main__':
  try:
    main(sys.argv)
  except RuntimeError as e:
    print('FATAL: %s' % e, file=sys.stderr)
    sys.exit(1)
