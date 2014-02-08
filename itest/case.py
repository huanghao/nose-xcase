# vim: set sw=4 ts=4 ai et:
import os
import sys
import time
import logging

import pexpect
if hasattr(pexpect, 'spawnb'): # pexpect-u-2.5
    spawn = pexpect.spawnb
else:
    spawn = pexpect.spawn

from itest.conf import settings
from itest.utils import now, cd, get_machine_labels

try:
    # 2.7
    from unittest.case import SkipTest
except ImportError:
    # 2.6 and below
    class SkipTest(Exception):
        """Raise this exception to mark a test as skipped.
        """
        pass


class TimeoutError(Exception):
    pass


def pcall(cmd, args=(), expecting=(), output=None, eof_timeout=None, output_timeout=None, **spawn_opts):
    '''call cmd with expecting
    expecting: list of pairs, first is expecting string, second is send string
    output: redirect cmd stdout and stderr to file object
    eof_timeout: timeout for whole cmd in seconds. None means block forever
    output_timeout: timeout if no output in seconds. Disabled by default
    spawn_opts: keyword arguments passed to spawn call
    '''
    question = [pexpect.EOF, pexpect.TIMEOUT]
    question.extend([ pair[0] for pair in expecting ])
    if output_timeout:
        question.append(r'\r|\n')
    answer = [None]*2 + [ i[1] for i in expecting ]

    start = time.time()
    child = spawn(cmd, list(args), **spawn_opts)
    if output:
        child.logfile_read = output

    timeout = output_timeout if output_timeout else eof_timeout
    try:
        while True:
            if output_timeout:
                cost = time.time() - start
                if cost >= eof_timeout:
                    msg = 'Run out of time in %s seconds!:%s %s' % \
                        (cost, cmd, ' '.join(args))
                    raise TimeoutError(msg)

            i = child.expect(question, timeout=timeout)
            if i == 0: # EOF
                break
            elif i == 1: # TIMEOUT
                if output_timeout:
                    msg = 'Hanging for %s seconds!:%s %s'
                else:
                    msg = 'Run out of time in %s seconds!:%s %s'
                raise TimeoutError(msg % (timeout, cmd, ' '.join(args)))
            elif output_timeout and i == len(question)-1:
                # new line, stands for any output
                # do nothing, just flush timeout counter
                pass
            else:
                child.sendline(answer[i])
    finally:
        child.close()

    return child.exitstatus


# enumerate patterns for all distributions
# fedora16-64:
# [sudo] password for itestuser5707:
# suse121-32b
# root's password:
# suse122-32b
# itestuser23794's password:
# u1110-32b
# [sudo] password for itester:
SUDO_PASS_PROMPT_PATTERN = '\[sudo\] password for .*?:|root\'s password:|.*?\'s password:'

def sudo(cmd):
    '''sudo command automatically input password'''
    cmd = 'sudo ' + cmd
    logging.info(cmd)

    expecting = [(SUDO_PASS_PROMPT_PATTERN, settings.SUDO_PASSWD)]
    return pcall(cmd, expecting=expecting, output=sys.stdout, eof_timeout=10)


class Tee(object):

    '''data write to original will write to another as well'''

    def __init__(self, original, another=sys.stdout):
        self.original = original
        self.another = another

    def write(self, data):
        self.another.write(data)
        return self.original.write(data)

    def flush(self):
        self.another.flush()
        return self.original.flush()

    def close(self):
        self.original.close()


class TestCase(object):
    '''Single test case'''

    meta = '.meta'
    count = 1
    was_skipped = False
    was_successful = False

    def __init__(self, fname, summary, steps,
                 setup='', teardown='',
                 qa=(), issue=None,
                 precondition='', tag='', version='',
                 conditions=None, fixtures=None,
                 ):
        self.version = version
        self.filename = fname
        self.summary = summary
        self.steps = steps

        self.setup = setup
        self.teardown = teardown

        self.qa = qa
        self.issue = issue if issue else {}
        self.conditions = conditions or {}
        self.fixtures = fixtures or ()

        self.component = self.guess_component(self.filename)
        #TODO: need a more reasonable and meaningful id rather than this
        self.id = hash(self)
        self.start_time = None
        self.logname = None
        self.logfile = None
        self.rundir = None

        self.steps_script = None
        self.setup_script = None
        self.teardown_script = None
        self.vars_script = None

    def __hash__(self):
        return hash(self.filename)

    def __eq__(self, that):
        return hash(self) == hash(that)

    def guess_component(self, filename):
        # assert that filename is absolute path
        if not settings.env_root or not filename.startswith(settings.cases_dir):
            return 'unknown'
        relative = filename[len(settings.cases_dir)+1:].split(os.sep)
        # >1 means [0] is an dir name
        return relative[0] if len(relative) > 1 else 'unknown'

    def _make_scripts(self):
        '''Make shell script of setup, teardown, steps
        '''
        self.setup_script =  self._make_setup_script()
        self.steps_script = self._make_steps_script()
        self.teardown_script = self._make_teardown_script()

    def _make_setup_script(self):
        if not self.setup:
            return

        code = '''cd %(rundir)s
(set -o posix; set) > %(var_old)s
set -x
%(setup)s
set +x
(set -o posix; set) > %(var_new)s
diff --unchanged-line-format= --old-line-format= --new-line-format='%%L' \\
    %(var_old)s %(var_new)s > %(var_out)s
''' % {'rundir': self.rundir,
       'var_old': os.path.join(self.meta, 'var.old'),
       'var_new': os.path.join(self.meta, 'var.new'),
       'var_out': os.path.join(self.meta, 'var.out'),
       'setup': self.setup,
       }
        return self._make_code('setup', code)

    def _make_steps_script(self):
        code = '''cd %(rundir)s
if [ -f %(var_out)s ]; then
    . %(var_out)s
fi
%(coverage)s
set -o pipefail
set -ex
%(steps)s
''' % {'rundir': self.rundir,
       'coverage': self._make_coverage_code(),
       'var_out': os.path.join(self.meta, 'var.out'),
       'steps': self.steps,
       }
        return self._make_code('steps', code)

    def _make_coverage_code(self):
        if not settings.ENABLE_COVERAGE or \
                not settings.env_root or \
                not settings.TARGET_NAME:
            return ''

        rcfile = os.path.join(settings.env_root, settings.COVERAGE_RCFILE)
        if os.path.exists(rcfile):
            opts = '--rcfile %s' % rcfile
        else:
            opts = ''

        target = settings.TARGET_NAME
        coverage_file = os.path.join(os.path.dirname(self.logname), '.coverage')

        code = '''
__ITEST_ORIG_TARGET__=$(which %(target)s)
shopt -s expand_aliases
coverage=$(which python-coverage 2>/dev/null || which coverage)
runsudo()
{
if [ $1 == %(target)s ]; then
shift
sudo COVERAGE_FILE=%(coverage_file)s $coverage run -p %(opts)s $(which %(target)s) "$@" && set -o pipefail
else
sudo "$@" && set -o pipefail
fi
}
alias sudo=runsudo
alias %(target)s='COVERAGE_FILE=%(coverage_file)s $coverage run -p %(opts)s '$__ITEST_ORIG_TARGET__
''' % {'target': target,
       'coverage_file': coverage_file,
       'opts': opts,
       }
        return code

    def _make_teardown_script(self):
        if not self.teardown:
            return

        code = '''cd %(rundir)s
if [ -f %(var_out)s ]; then
    . %(var_out)s
fi
set -x
%(teardown)s
''' % {'rundir': self.rundir,
       'var_out': os.path.join(self.meta, 'var.out'),
       'teardown': self.teardown,
       }
        return self._make_code('teardown', code)

    def _setup(self):
        if self.setup_script:
            self._log('INFO: setup start')
            self._psh(self.setup_script)
            self._log('INFO: setup finish')

    def _steps(self):
        self._log('INFO: steps start')
        retu = self._psh(self.steps_script, self.qa)
        self._log('INFO: steps finish')
        return retu

    def _teardown(self):
        if self.teardown_script:
            self._log('INFO: teardown start')
            self._psh(self.teardown_script)
            self._log('INFO: teardown finish')

    def _psh(self, script, more_expecting=()):
        expecting = [(SUDO_PASS_PROMPT_PATTERN, settings.SUDO_PASSWD)] + list(more_expecting)
        try:
            return pcall('/bin/bash',
                         [script],
                         expecting=expecting,
                         output=self.logfile,
                         eof_timeout=float(settings.RUN_CASE_TIMEOUT),
                         output_timeout=float(settings.HANGING_TIMEOUT),
                         )
        except Exception as err:
            self._log('ERROR: pcall error:%s\n%s' % (script, err))
            return -1

    def run(self, result, space, verbose):
        result.test_start(self)
        try:
            self._check_conditions()
            # FIXME: make this self.rundir as local var
            self.rundir = space.new_test_dir(self.version,
                                             os.path.dirname(self.filename),
                                             self.fixtures)
            with cd(self.rundir):
                os.mkdir(self.meta)
                self._open_log(verbose)
                self._make_scripts()
                self._log('INFO: case start to run!')
                self._setup()
                try:
                    exit_status = self._steps()
                finally:
                    # make sure to call tearDown if setUp success
                    self._teardown()
                    self._log('INFO: case is finished!')
        except SkipTest as err:
            result.add_skipped(self, err)
        except KeyboardInterrupt:
            # mark case as failure if it is broke by ^C
            result.add_failure(self)
            raise
        except:
            # catch all exceptions and log it, no need to throw it out
            result.add_exception(self, sys.exc_info())
            # FIXME: add_error not add_exception
        else:
            if exit_status == 0:
                result.add_success(self)
            else:
                result.add_failure(self)
        finally:
            # make sure to call test_stop if test_start is called
            result.test_stop(self)
            if self.logfile:
                self.logfile.close()
                self.delete_color_code_in_log_file(self.logname)

    def _open_log(self, verbose):
        self.logname = os.path.join(self.rundir, self.meta, 'log')
        self.logfile = open(self.logname, 'a')
        if verbose > 1:
            self.logfile = Tee(self.logfile)

    def _log(self, msg):
        self.logfile.write('%s [itest] %s\n' % (now(), msg))

    def delete_color_code_in_log_file(self, fname):
        os.system("sed -i 's/\x1b\[[0-9]*m//g' %s" % fname)
        os.system("sed -i 's/\x1b\[[0-9]*K//g' %s" % fname)

    def _make_code(self, name, code):
        path = os.path.join(self.meta, name)
        data = code.encode('utf8') if isinstance(code, unicode) else code
        with open(path, 'w') as f:
            f.write(data)
        return path

    def _check_conditions(self):
        '''Check if conditions match, raise SkipTest if some conditions are
        defined but not match.
        '''
        labels = set((i.lower() for i in get_machine_labels()))

        # blacklist has higher priority, if it match both black and white
        # lists, it will be skipped
        intersection = labels & self.conditions.get('distblacklist', set())
        if intersection:
            raise SkipTest('by distribution blacklist:%s' %
                           ','.join(intersection))

        kw = 'distwhitelist'
        if kw in self.conditions:
            intersection = labels & self.conditions[kw]
            if not intersection:
                raise SkipTest('not in distribution whitelist:%s' %
                               ','.join(self.conditions[kw]))
