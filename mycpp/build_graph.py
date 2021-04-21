#!/usr/bin/env python2
"""
build_graph.py

Code Layout:

  build_graph.py  # This file describes dependencies programmatically
  build.ninja     # Generated build description ('rule' and 'build')
  build-steps.sh  # Invoked by Ninja rules

  build.sh        # wrappers invoked by the Toil and devtools/release.sh

Data Layout:

  examples/
    cgi.py
    varargs.py
    varargs_preamble.h

  _ninja/
    gen/ 
      varargs_raw.cc
      varargs.cc
    bin/          # binaries
      examples/   # many variants
      examples-stripped/
      unit/       # unit tests
    tasks/        # *.txt and *.task.txt for .wwz
      typecheck/  # optionally run
      test/       # py, gc_debug, asan, opt
      benchmark/
      unit/

      # optionally logged?
      translate/
      compile/

  Phony Targets
    typecheck, strip, bencmark-table, etc. (See phony dict below)

Also:

- .wwz archive of all the logs.
- Turn it into HTML and link to logs.  Basically just like Toil does.

Notes for Oil: 

- escape_path() in ninja_syntax seems wrong?
  - It should really take $ to $$.
  - It doesn't escape newlines

    return word.replace('$ ', '$$ ').replace(' ', '$ ').replace(':', '$:')

  Ninja shouldn't have used $ and ALSO used shell commands (sh -c)!  Better
  solutions:

  - Spawn a process with environment variables.
  - use % for substitution instead

- Another problem: Ninja doesn't escape the # comment character like $#, so
  how can you write a string with a # as the first char on a line?
"""

from __future__ import print_function

import os
import sys

sys.path.append('../vendor')
import ninja_syntax


def log(msg, *args):
  if args:
    msg = msg % args
  print(msg, file=sys.stderr)


# special ones in examples.sh:
# - parse
# - lexer_main -- these use Oil code
# - pgen2_demo -- uses pgen2

def ShouldSkipBuild(name):
  if name in [
      # these 3 use Oil code, and don't type check or compile
      # Maybe give up on these?  pgen2_demo might be useful later.
      'lexer_main', 
      'pgen2_demo',

      # TODO: make this compile.  It's a realistic example.
      # - expr.asdl when GC=1
      # - qsn_qsn.h is incompatible.  This is also an issue with
      #   'asdl/run.sh gc-test'
      'parse',
      ]:
    return True

  return False


def ExamplesToBuild():

  filenames = os.listdir('examples')
  py = [name[:-3] for name in filenames if name.endswith('.py')]

  to_test = [name for name in py if not ShouldSkipBuild(name)]

  return to_test


def ShouldSkipTest(name):
  # '%5d' doesn't work yet.  TODO: fix this.
  if name == 'strings':
    return True

  return False


def ShouldSkipBenchmark(name):
  if name.startswith('test_'):
    return True

  # BUG: 8191 exceptions problem, I think caused by Alloc<ParseError>
  if name == 'control_flow':
    return True

  # BUG: Assertion failure here!
  if name == 'cartesian':
    return True

  # BUG: Different number of iterations!
  if name == 'files':
    return True

  return False


RUNTIME = ['my_runtime.cc', 'mylib2.cc', 'gc_heap.cc']

UNIT_TESTS = {
    'mylib_test': ['mylib.cc'],
    'gc_heap_test': ['gc_heap.cc'],
    'gc_stress_test': RUNTIME,
    'my_runtime_test': RUNTIME,
    'mylib2_test': RUNTIME,

    # lives in demo/target_lang.cc
    'target_lang': ['../cpp/dumb_alloc.cc', 'gc_heap.cc'],
}

TRANSLATE_FILES = {
    'modules': ['testpkg/module1.py', 'testpkg/module2.py'],
}

EXAMPLE_CXXFLAGS = {
    # TODO: simplify this
    'varargs': "'-I ../cpp -I ../_build/cpp -I ../_devbuild/gen'",

    'parse': "'-I ../cpp -I ../_build/cpp'",
}

EXAMPLES_PY = {
    'parse': [],  # added dynamically
}

EXAMPLES_CC = {
    # for now, we don't include the header
    'parse': ['_ninja/asdl/expr_asdl.cc'],
}

def main(argv):
  n = ninja_syntax.Writer(open('build.ninja', 'w'))

  n.comment('Translate, compile, and test mycpp examples.')
  n.comment('Generated by %s.' % os.path.basename(__file__))
  n.newline()

  n.rule('touch',
         command='touch $out',
         description='touch $out')
  n.newline()
  n.rule('asdl-mypy',
         command='./build-steps.sh asdl-mypy $in $out',
         description='asdl-mypy $in $out')
  n.newline()
  n.rule('asdl-cpp',
         command='./build-steps.sh asdl-cpp $in $out_prefix',
         description='asdl-cpp $in $out_prefix')
  n.newline()
  n.rule('translate',
         command='./build-steps.sh translate $out $in',
         description='translate $out $in')
  n.newline()
  n.rule('wrap-cc',
         command='./build-steps.sh wrap-cc $name $in $preamble_path $out',
         description='wrap-cc $name $in $preamble_path $out')
  n.newline()
  n.rule('compile',
         # note: $in can be MULTIPLE files, shell-quoted
         command='./build-steps.sh compile $variant $out $more_cxx_flags $in',
         description='compile $variant $out $more_cxx_flags $in')
  n.newline()
  n.rule('strip',
         # TODO: there could be 2 outputs: symbols + binary
         command='./build-steps.sh strip_ $in $out',
         description='strip $in $out')
  n.newline()
  n.rule('task',
         # note: $out can be MULTIPLE FILES, shell-quoted
         command='./build-steps.sh task $in $out',
         description='task $in $out')
  n.newline()
  n.rule('example-task',
         # note: $out can be MULTIPLE FILES, shell-quoted
         command='./build-steps.sh example-task $name $impl $bin $out',
         description='example-task $name $impl $bin $out')
  n.newline()
  n.rule('typecheck',
         command='./build-steps.sh typecheck $main_py $out',
         description='typecheck $main_py $out')
  n.newline()
  n.rule('logs-equal',
         command='./build-steps.sh logs-equal $out $in',
         description='logs-equal $out $in')
  n.newline()
  n.rule('benchmark-table',
         command='./build-steps.sh benchmark-table $out $in',
         description='benchmark-table $out $in')
  n.newline()

  examples = ExamplesToBuild()
  #examples = ['cgi', 'containers', 'fib_iter']
  #examples = ['cgi']

  # Groups of targets.  Not all of these are run by default.
  phony = {
      'unit': [],
      'typecheck': [],  # optional: for debugging only.  translation does it.

      # Note: unused
      'test': [],  # test examples (across variants, including Python)

      'benchmark-table': [],

      # Compare logs for tests AND benchmarks.
      # It's a separate task because we have multiple variants to compare, and
      # the timing of test/benchmark tasks should NOT include comparison.
      'logs-equal': [],

      'strip': [],  # optional: strip binaries.  To see how big they are.
  }

  #
  # Build and run unit tests
  #

  for test_name in sorted(UNIT_TESTS):
    cc_files = UNIT_TESTS[test_name]

    # TODO: doesn't run under pure 'asan' because of -D GC_DEBUG, etc.
    for variant in ['gc_debug']:  # , 'asan', 'opt']:
      b = '_ninja/bin/unit/%s.%s' % (test_name, variant)

      if test_name == 'target_lang':  # SPECIAL CASE
        main_cc = 'demo/target_lang.cc'
      else:
        main_cc = '%s.cc' % test_name

      n.build([b], 'compile', [main_cc] + cc_files,
              variables=[('variant', variant), ('more_cxx_flags', "''")])
      n.newline()

      prefix = '_ninja/tasks/unit/%s.%s' % (test_name, variant)
      task_out = '%s.task.txt' % prefix
      log_out = '%s.log.txt' % prefix
      n.build([task_out, log_out], 'task', b)
      n.newline()

      phony['unit'].append(task_out)

  #
  # ASDL schema that examples/parse.py depends on
  #

  p = '_ninja/asdl/expr_asdl.py'
  n.build(p, 'asdl-mypy', 'examples/expr.asdl')
  EXAMPLES_PY['parse'].append(p)

  # This is annoying
  for p in ['_ninja/__init__.py', '_ninja/asdl/__init__.py']:
    n.build(p, 'touch')
    EXAMPLES_PY['parse'].append(p)

  prefix = '_ninja/asdl/expr_asdl'
  n.build([prefix + '.cc', prefix + '.h'], 'asdl-cpp', 'examples/expr.asdl',
          variables=[('out_prefix', prefix)])

  #
  # Build and run examples/
  #

  to_compare = []
  benchmark_tasks = []

  for ex in examples:
    n.comment('---')
    n.comment(ex)
    n.comment('---')
    n.newline()

    # TODO: make a phony target for these, since they're not strictly necessary.
    # Translation does everything that type checking does.  Type checking only
    # is useful for debugging.
    t = '_ninja/tasks/typecheck/%s.log.txt' % ex
    main_py = 'examples/%s.py' % ex
    n.build([t], 'typecheck', 
            EXAMPLES_PY.get(ex, []) + [main_py],
            variables=[('main_py', main_py)])
    n.newline()
    phony['typecheck'].append(t)

    # Run Python.
    for mode in ['test', 'benchmark']:
      prefix = '_ninja/tasks/%s/%s.py' % (mode, ex)
      task_out = '%s.task.txt' % prefix

      if mode == 'benchmark':
        if ShouldSkipBenchmark(ex):
          log('Skipping benchmark of %s', ex)
          continue
        benchmark_tasks.append(task_out)

      elif mode == 'test':
        if ShouldSkipTest(ex):
          log('Skipping test of %s', ex)
          continue

      log_out = '%s.log.txt' % prefix
      n.build([task_out, log_out], 'example-task',
              EXAMPLES_PY.get(ex, []) + ['examples/%s.py' % ex],
              variables=[
                  ('bin', main_py),
                  ('name', ex), ('impl', 'Python')])

      n.newline()

    raw = '_ninja/gen/%s_raw.cc' % ex

    # Translate to C++
    n.build(raw, 'translate',
            TRANSLATE_FILES.get(ex, []) + ['examples/%s.py' % ex])

    p = 'examples/%s_preamble.h' % ex
    # Ninja empty string!
    preamble_path = p if os.path.exists(p) else "''"

    # Make a translation unit
    n.build('_ninja/gen/%s.cc' % ex, 'wrap-cc', raw,
            variables=[('name', ex), ('preamble_path', preamble_path)])

    n.newline()

    more_cxx_flags = EXAMPLE_CXXFLAGS.get(ex, "''")

    # Compile C++. TODO: Can also parameterize by CXX: Clang or GCC.
    for variant in ['gc_debug', 'asan', 'opt']:
      b = '_ninja/bin/examples/%s.%s' % (ex, variant)
      n.build(
          b, 'compile',
          ['_ninja/gen/%s.cc' % ex] + RUNTIME + EXAMPLES_CC.get(ex, []),
          variables=[
              ('variant', variant), ('more_cxx_flags', more_cxx_flags)
          ])
      n.newline()

      if variant == 'opt':
        stripped = '_ninja/bin/examples-stripped/%s.%s' % (ex, variant)
        n.build(stripped, 'strip', [b],
                variables=[('variant', variant)])
        n.newline()
        phony['strip'].append(stripped)

    # minimal
    MATRIX = [
        ('test', 'asan'),
        ('benchmark', 'opt'),
    ]

    # Run the binary in two ways
    for mode, variant in MATRIX:
      task_out = '_ninja/tasks/%s/%s.%s.task.txt' % (mode, ex, variant)

      if mode == 'benchmark':
        if ShouldSkipBenchmark(ex):
          log('Skipping benchmark of %s', ex)
          continue
        benchmark_tasks.append(task_out)

      elif mode == 'test':
        if ShouldSkipTest(ex):
          log('Skipping test of %s', ex)
          continue

      log_out = '_ninja/tasks/%s/%s.%s.log.txt' % (mode, ex, variant)
      py_log_out = '_ninja/tasks/%s/%s.py.log.txt' % (mode, ex)

      to_compare.append(log_out)
      to_compare.append(py_log_out)

      n.build([task_out, log_out], 'example-task',
              '_ninja/bin/examples/%s.%s' % (ex, variant),
              variables=[
                ('bin', '_ninja/bin/examples/%s.%s' % (ex, variant)),
                ('name', ex), ('impl', 'C++')])
      n.newline()

  # Compare the log of all examples
  out = '_ninja/logs-equal.txt'
  n.build([out], 'logs-equal', to_compare)
  n.newline()

  phony['logs-equal'].append(out)

  # Timing of benchmarks
  out = '_ninja/benchmark-table.tsv'
  n.build([out], 'benchmark-table', benchmark_tasks)
  n.newline()

  phony['benchmark-table'].append(out)

  #
  # Write phony rules we accumulated
  #

  phony_real = []
  for name in sorted(phony):
    deps = phony[name]
    if deps:
      n.build([name], 'phony', deps)
      n.newline()

      phony_real.append(name)

  n.default(['unit', 'logs-equal', 'benchmark-table'])

  # All groups
  n.build(['all'], 'phony', phony_real)


if __name__ == '__main__':
  try:
    main(sys.argv)
  except RuntimeError as e:
    print('FATAL: %s' % e, file=sys.stderr)
    sys.exit(1)