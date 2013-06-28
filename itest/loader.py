import os
import re

from itest.case import TestCase
from itest.suite import TestSuite


class BaseParser(object):

    HEADER_PATTERN = re.compile(r'^__([a-zA-Z0-9]+?)__(\s*:)?', re.M)

    def sections_iter(self, text):
        '''Return a generator whose value is (section_name, section_content).

        Syntax:
        A section is consists of a header and its content. Sections can't be nested,
        where there is a new section begins, the previous one will be automatically
        ended.

        Section name is case insensitive, only alphabets and digits are permitted,
        it should at least contain one character. It should start with __ (two
        underscores) and also ends with __, an optional comma at the end is also
        allowed.

        For example:
            __summary__
            __summary__:
            __Summary__
            __SUMMARY__
        These are all the same section header whose name is "summary".
        '''

        prev = None
        for match in re.finditer(self.HEADER_PATTERN, text):
            name = match.group(1)
            pos = match.start(0)

            # content starts at where the header ends
            content_start = match.end(0)

            if prev:
                prevn, prevs = prev
                # content ends at where next header starts
                yield prevn, text[prevs:pos]

            prev = (name.lower(), content_start)

        if prev:
            prevn, prevs = prev
            yield prevn, text[prevs:]

    def parse(self, text):
        '''
        Return a dict whose keys are section names, whose values are contents.

        It calls the method "self.clean_${section_name}" with corresponding
        section content if this method exists when parsing a section. If this
        method doesn't exist, content will be original text.

        It calls "self.clean" with a dict contains all section names and
        contents to do final cleanup.

        Subclasses can overwrite these clean* methods to do customized parsing.
        '''

        sec = {}
        for name, content in self.sections_iter(text):
            handler = getattr(self, 'clean_%s' % name, None)
            if handler:
                content = handler(content)
            sec[name] = content

        clean = getattr(self, 'clean', None)
        if clean:
            clean(sec)

        return sec


class CaseParser(BaseParser):

    REQUIRED_SECTIONS = ('summary', 'steps')

    def clean(self, sec):
        for name in self.REQUIRED_SECTIONS:
            if name not in sec:
                raise SyntaxError('"%s" section is required' % name)

    def clean_summary(self, text):
        return text.strip()

    def clean_qa(self, text):
        text = text.strip()
        if not text:
            return []

        qa = []
        state = 0
        question = None
        answer = None

        for line in text.splitlines():
            line = line.rstrip(os.linesep)
            if not line:
                continue

            if state == 0 and line.startswith('Q:'):
                question = line[len('Q:'):].lstrip()
                state = 1
            elif state == 1 and line.startswith('A:'):
                # add os.linesep here to simulate user input enter
                answer = line[len('A:'):].lstrip()
                state = 2
            elif state == 2 and line.startswith('Q:'):
                qa.append((question, answer))
                question = line[len('Q:'):].lstrip()
                state = 1
            else:
                raise SyntaxError('Invalid format of QA:%s' % line)

        if state == 2:
            qa.append((question, answer))

        return qa

    def clean_issue(self, text):
        text = text.strip()
        if not text:
            return {}

        nums = {}
        issues = text.replace(',', ' ').split()
        for issue in issues:
            m = re.match(r'(#|issue|feature|bug|((c|C)(hange)?))?-?(\d+)', issue, re.I)
            if m:
                nums[m.group()] = m.group(5)

        if not nums:
            raise SyntaxError('Unrecognized issue number:%s' % text)
        return nums


class TestLoader(object):

    def load_args(self, args, env):
        '''load test from all args'''
        if not args:
            path = os.path.join(env.ENV_PATH, env.CASES_DIR)
            return self.load(path, env)

        suite = TestSuite()
        for arg in args:
            suite.add_test(self.load(arg, env))
        return suite

    def load(self, sel, env):
        '''load a single test pattern'''
        def _is_test(ret):
            return isinstance(ret, TestSuite) or isinstance(ret, TestCase)

        suite = TestSuite()
        stack = [sel]

        while stack:
            sel = stack.pop()
            for pattern in suite_patterns.all():
                if callable(pattern):
                    pattern = pattern()

                ret = pattern.load(sel, env)
                if not ret:
                    continue

                if _is_test(ret):
                    suite.add_test(ret)
                elif isinstance(ret, list):
                    stack.extend(ret)
                else:
                    stack.append(ret)
                break

        return suite


class AliasPattern(object):
    '''dict key of settings.SUITES is alias for its value'''

    def load(self, sel, env):
        if sel in env.SUITES:
            return env.SUITES[sel]


class FilePattern(object):
    '''test from file name'''

    case_parser_class = CaseParser

    def load(self, name, _env):
        if not os.path.isfile(name):
            return

        path = os.path.abspath(name)
        with open(path) as f:
            text = f.read()

        parser = self.case_parser_class()
        sec = parser.parse(text)

        return TestCase(path, **sec)


class DirPattern(object):
    '''find all tests recursively in a dir'''

    def load(self, top, _env):
        if os.path.isdir(top):
            return list(self._walk(top))

    def _walk(self, top):
        for current, _dirs, nondirs in os.walk(top):
            for name in nondirs:
                if name.endswith('.case'):
                    yield os.path.join(current, name)


class ComponentPattern(object):
    '''tests from a component name'''

    _components = None

    @staticmethod
    def guess_components(env):
        comp = []
        path = os.path.join(env.ENV_PATH, env.CASES_DIR)
        for base in os.listdir(path):
            full = os.path.join(path, base)
            if os.path.isdir(full):
                comp.append(base)
        return set(comp)

    @classmethod
    def is_component(cls, comp, env):
        if cls._components is None:
            cls._components = cls.guess_components(env)
        return comp in cls._components

    def load(self, comp, env):
        if self.is_component(comp, env):
            return os.path.join(env.ENV_PATH, env.CASES_DIR, comp)


class InversePattern(object):
    '''string starts with "!" is the inverse of string[1:]'''

    def load(self, sel, env):
        if sel.startswith('!'):
            comp = sel[1:]
            if ComponentPattern.is_component(comp, env):
                comps = ComponentPattern.guess_components(env)
                return [c for c in comps if c != comp]


class IntersectionPattern(object):
    '''use && load intersection set of many parts'''

    loader_class = TestLoader

    def load(self, sel, env):
        if sel.find('&&') <= 0:
            return

        def intersection(many):
            inter = None
            for each in many:
                if inter is None:
                    inter = set(each)
                else:
                    inter.intersection_update(each)
            return inter

        loader = self.loader_class()
        many = [ loader.load(part, env)
                for part in sel.split('&&') ]

        return TestSuite(intersection(many))


class _SuitePatternRegister(object):

    def __init__(self):
        self._patterns = []

    def register(self, cls):
        self._patterns.append(cls)

    def all(self):
        return self._patterns


def register_default_patterns():
    for pattern in (AliasPattern,
                    FilePattern,
                    DirPattern,
                    IntersectionPattern,
                    ComponentPattern,
                    InversePattern,
                    ):
        suite_patterns.register(pattern)

suite_patterns = _SuitePatternRegister()
register_default_patterns()