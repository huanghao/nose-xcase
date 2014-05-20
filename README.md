[![Build Status](https://travis-ci.org/huanghao/nose-xcase.svg?branch=master)](https://travis-ci.org/huanghao/nose-xcase)

=====

prepare for test environment
----------------------------
# itest will use this password to run sudo
export ITEST_SUDO_PASSWORD
export http_proxy, https_proxy, no_proxy

running gbs test cases
----------------------
1. run all test cases
  $ runtest

2. print detail message when running test cases
  $ runtest -v

3. print log when runing test cases, useful for debuging
  $ runtest -vv data/auto/changelog/test_changelog_since.gbs

4. run test suites
  $ runtest chroot export

5. run single test case and test suites
  $ runtest data/auto/build/test_build_commit_ia32.gbs import submit

6. check test results
  $ runtest chroot submit changelog auto/build/test_build_help.gbs
........................

Ran 24 tests in 0h 00 min 10s

OK

Details
---------------------------------
Component      Passed   Failed
build          1        0
remotebuild    0        0
changelog      7        0
chroot         2        0
import         0        0
export         0        0
submit         14       0
conf           0        0


Syntax of case
==============

\_\_steps\_\_
-------------

*steps* is the core section of a case.  It consist of command lines and
comments. A lines starting with '>' is called command line. Others are all
treated as comments. Comments are only for reading, they will be ignored in
running.

Each command line runs one by one in the same order as they occur in case. If
any command exit with nonzero, the whole case will exit immediately and is
treated as failed. The only condition that a case pass is when the last command
exit with code 0. 

For example:

    > echo 1
    > false | echo 2
    > echo 3

"echo 3" never run, it fail in the second line.

When you want to assert a command will fail, add "!" before it, and enclose with
parenthesis(subshell syntax).

    > echo 1
    > (! false | echo 2)
    > echo 3

This case pass, because the designer assert that the second will fail via "!".
Parenthesis are required, which makes the whole line a subshell and the subshell
exit with 0. When parenthesis are missing, this case will fail in the second
line(same as the above example).

NOTE: Itest use "bash -xe" and "set -o pipefall" to implement this, please refer
bash manual for more detail.

\_\_setup\_\_
-------------
This is an optional section which can be used to set up environment need
by following steps. Its content should be valid shell code.

Variables declared in this section can also be used in *steps* and *teardown*
sections. In constract, variables defined in *steps* can't be seen in the
scope of *teardown*, so if there are common variables, they should be set
in this section.

For example:

    __vars__:
    temp_project_name=test_$(date +%Y%m%d)_$RANDOM
    touch another_temp_file

    __steps__:
    > gbs remotebuild -T $temp_project_name

    __teardown__:
    rm -f another_temp_file
    osc delete $temp_project

\_\_teardown\_\_
----------------
This is also an optional section which can be used to clean up environment
after *steps* finish. Its content should be valid shell code.

Whatever *steps* failed or successed, this section gaurantee to be run.
Result of this section doesn't affect result of the case.
