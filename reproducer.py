import csv
import json
import git
import os
try:
    from mvnpy.Repo import Repo
except:
    from Repo import Repo
from subprocess import Popen
from dir_structure import DirStructure, DirId
import networkx
from sfl.sfl.Diagnoser.diagnoserUtils import write_json_planning_file, read_json_planning_file
try:
    from mvnpy.jcov_parser import JcovParser
except:
    from jcov_parser import JcovParser
import sys
try:
    from javadiff.SourceFile import SourceFile
except:
    from javadiff.javadiff.SourceFile import SourceFile



class Reproducer(object):
    D4J_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), r"projects"))
    D4J_JSON = os.path.realpath(os.path.join(os.path.dirname(__file__), r"defects4j-bugs.json"))

    def __init__(self, id, failing_tests, dir_id):
        self.id = id
        self.dir_id = dir_id
        self.surefire_tests = []
        self.tests_to_trace = []
        self.test_traces = []
        self.optimized_traces = []
        self.bugs = []
        self.failing_tests = failing_tests

    def get_tests_to_trace(self):
        return self.tests_to_trace

    def get_id(self):
        return self.id

    def get_surefire_tests(self):
        return self.surefire_tests

    def get_dir_id(self):
        return self.dir_id

    def get_repo(self):
        pass

    def clone(self):
        pass

    def get_patches_dir(self):
        pass

    def apply_patch(self):
        pass

    def fix(self):
        pass

    def read_test_results(self):
        repo = Repo(self.get_dir_id().clones)
        self.surefire_tests = repo.observe_tests()

    def clean_execution(self):
        repo = Repo(self.get_dir_id().clones)
        build_report = repo.install()
        with open(self.get_dir_id().mvn_outputs, "w") as f:
            f.write(build_report)

    def trace(self, trace_failed=False):
        repo = Repo(self.get_dir_id().clones)
        DirStructure.mkdir(self.get_dir_id().traces)
        if self.test_traces:
            return
        if self.is_marked() and False:
            traces = list(JcovParser(self.get_dir_id().traces, short_type=True).parse())
        else:
            tests_to_run = map(lambda t: ".".join(t.split('.')[:5]) + '*', self.failing_tests)
            tests = tests_to_run if trace_failed else None
            self.clear()
            traces = list(repo.run_under_jcov(self.get_dir_id().traces, False, instrument_only_methods=True, short_type=True, tests_to_run=tests, check_comp_error=False))
        self.test_traces = dict(map(lambda t: (t.test_name, t), traces))

    def get_optimized_traces(self):
        self.trace()
        self.extract_tests_to_trace()
        all_tests = filter(lambda x: x, map(self.test_traces.get, self.tests_to_trace))
        fail_tests = filter(lambda test: self.get_surefire_tests()[test.test_name].outcome in self.get_non_pass_outcomes(), all_tests)
        fail_components = reduce(set.__or__, map(lambda test: set(test.get_trace()), fail_tests), set())
        self.optimized_traces = dict(map(lambda t: (t.test_name, t), filter(lambda test: fail_components & set(test.get_trace()), all_tests)))

    def get_failing_tests_as_surefire_tests(self):
        failing_tests = []
        surefire_tests = self.get_surefire_tests().keys()
        for test in self.failing_tests:
            surefire_test = list(filter(lambda t: test.lower() in t.lower(), surefire_tests))
            if len(surefire_test) != 1:
                surefire_test = list(filter(lambda t: test.lower() == t.lower(), surefire_tests))
            if len(surefire_test) != 1:
                return []
            failing_tests.append(surefire_test[0])
        return failing_tests

    def extract_tests_to_trace(self):
        self.read_test_results()
        failing_tests = self.get_failing_tests_as_surefire_tests()
        if not failing_tests:
            raise Exception("no failed tests")
        self.tests_to_trace = []
        for test in self.get_surefire_tests():
            add = False
            if self.get_surefire_tests()[test].outcome in self.get_non_pass_outcomes():
                add = test in failing_tests
            elif self.get_surefire_tests()[test].outcome == 'pass':
                add = test not in failing_tests
            if add:
                self.tests_to_trace.append(test)
        return True

    def get_non_pass_outcomes(self):
        return ['failure', 'error']

    def get_buggy_functions(self, extract_always=False):
        if self.is_marked() and os.path.exists(self.get_dir_id().bugs) and extract_always:
            with open(self.get_dir_id().bugs) as f:
                self.bugs = json.loads(f.read())
        else:
            self.bugs = self.extract_buggy_functions()
            with open(self.get_dir_id().bugs, "wb") as f:
                json.dump(self.bugs, f)
        if self.bugs:
            return True
        return False

    def extract_buggy_functions(self):
        return self.bugged_components

    def clear(self):
        # git.Repo(self.get_dir_id().clones).git.checkout('--', '.')
        pass

    def mark(self):
        with open(self.get_dir_id().mark, "w") as f:
            f.write("executed_succesfully")

    def is_marked(self):
        return self.get_dir_id().is_marked()

    def dump(self):
        if self.is_marked():
            return
        self.clone()
        self.clear()
        self.apply_patch()
        if not self.get_buggy_functions():
            raise Exception("get_buggy_functions")
        self.fix()
        self.clean_execution()
        if self.extract_tests_to_trace():
            self.trace()
            if self.extract_tests_to_trace():
                self.mark()
                self.save_as_sfl_matrix()
                self.save_tests_results()

    def save_as_sfl_matrix(self):
        if self.is_marked():
            self.get_optimized_traces()
            self.get_buggy_functions(True)
            tests_details = []
            bugs = map(lambda b: b.replace(',', ';'), self.bugs)
            for test in self.optimized_traces.values():
                nice_trace = list(set(map(
                    lambda t: t.lower().replace("java.lang.", "").replace("java.io.", "").replace("java.util.", ""),
                    test.get_trace())))
                if test.test_name + "()" in nice_trace:
                    nice_trace.remove(test.test_name + "()")
                tests_details.append((test.test_name, nice_trace, 0 if self.get_surefire_tests()[test.test_name].outcome == 'pass' else 1))
            write_json_planning_file(self.get_dir_id().matrices, tests_details, bugs)

    def get_files_packages(self):
        sources_path = r'src/main/java'
        packages = dict()
        repo = git.Repo(self.get_dir_id().clones)
        for file_name in filter(lambda f: sources_path in f, repo.git.ls_files().split('\n')):
            packages[os.path.normpath(file_name.split('.java')[0].split(sources_path)[1]).replace(os.sep, '.')[1:]] = file_name
        with open(self.get_dir_id().files_packages, "wb") as f:
            json.dump(packages, f)
        return packages

    def get_files_commits(self):
        sources_path = r'src/main/java'
        test_sources_path = r'src/test/java'
        commits = dict()
        repo = git.Repo(self.get_dir_id().clones)
        repo_commits = map(lambda x: x.hexsha[:7], list(repo.iter_commits()))
        for file_name in filter(lambda f: sources_path in f or test_sources_path in f, repo.git.ls_files().split('\n')):
            file_commits = map(lambda x: x[:7], repo.git.log('--pretty=format:%h', file_name).split('\n'))
            commits[file_name] = map(lambda c: 1 if c in file_commits else 0, repo_commits)
        with open(self.get_dir_id().files_commits, "wb") as f:
            json.dump(commits, f)
        return commits

    def get_files_functions(self):
        sources_path = r'src/main/java'
        test_sources_path = r'src/test/java'
        repo = git.Repo(self.get_dir_id().clones)
        files_functions = {}
        for file_name in filter(lambda f: sources_path in f or test_sources_path in f, repo.git.ls_files().split('\n')):
            try:
                with open(os.path.join(self.get_dir_id().clones, file_name)) as f:
                    map(lambda m: files_functions.setdefault(m.id.split("@")[1].lower().replace(',', ';'), file_name), SourceFile(f.read(), file_name).methods.values())
            except:
                pass
        with open(self.get_dir_id().files_functions, "wb") as f:
            json.dump(files_functions, f)

    def generate_javadoc(self):
        repo = Repo(self.get_dir_id().clones)
        repo.javadoc_command(self.get_dir_id().javadoc)

    def execution_graph(self):
        DirStructure.mkdir(self.get_dir_id().execution_graphs)
        for trace in self.optimized_traces:
            g = networkx.DiGraph()
            g.add_edges_from(self.optimized_traces[trace].get_execution_edges())
            networkx.write_gexf(g, os.path.join(self.get_dir_id().execution_graphs, trace + ".gexf"))

    def call_graph(self):
        DirStructure.mkdir(self.get_dir_id().call_graphs)
        for trace in self.optimized_traces:
            g = networkx.DiGraph()
            g.add_edges_from(self.optimized_traces[trace].get_call_graph_edges())
            networkx.write_gexf(g, os.path.join(self.get_dir_id().call_graphs, trace + ".gexf"))

    def data_extraction(self):
        if not self.is_marked():
            return
        self.get_optimized_traces()
        self.call_graph()
        self.execution_graph()
        self.generate_javadoc()
        self.get_files_commits()
        self.get_files_packages()
        self.get_files_functions()
        self.labels()
        self.save_traces()

    def labels(self):
        self.extract_tests_to_trace()
        self.get_buggy_functions()
        labels = {}
        bugs = map(lambda b: b.replace(',', ';'), self.bugs)
        for test in self.optimized_traces.values():
            nice_trace = list(set(map(
                lambda t: t.lower().replace("java.lang.", "").replace("java.io.", "").replace("java.util.", ""),
                test.get_trace())))
            for bug in filter(nice_trace.__contains__, bugs):
                labels.setdefault(test.test_name, dict())[bug] = self.get_surefire_tests()[test.test_name].outcome == 'pass'
        with open(self.get_dir_id().labels, "wb") as f:
            json.dump(labels, f)

    def save_traces(self):
        if self.is_marked():
            self.get_optimized_traces()
            traces = dict()
            for test in self.optimized_traces.values():
                nice_trace = list(set(map(
                    lambda t: t.lower().replace("java.lang.", "").replace("java.io.", "").replace("java.util.", ""),
                    test.get_trace())))
                traces[test.test_name] = nice_trace
                if test.test_name + "()" in nice_trace:
                    nice_trace.remove(test.test_name + "()")
            with open(self.get_dir_id().traces_json, "wb") as f:
                json.dump(traces, f)

    def save_tests_results(self):
        if self.is_marked():
            self.get_optimized_traces()
            data = dict(map(lambda t: (t, self.get_surefire_tests()[t].outcome == 'pass'), self.optimized_traces))
            with open(self.get_dir_id().tests_results, "wb") as f:
                json.dump(data, f)

    def do_all(self):
        self.dump()
        self.data_extraction()
        if self.is_marked():
            from feature_extraction import FeatureExtraction
            FeatureExtraction(self.get_dir_id()).extract()

    def get_training_set(self):
        from feature_extraction import FeatureExtraction
        FeatureExtraction(self.get_dir_id()).get_training_set()

    def get_testing_set(self):
        from feature_extraction import FeatureExtraction
        FeatureExtraction(self.get_dir_id()).get_testing_set()

    def experiment(self):
        from experiment import ExperimentMatrix
        ExperimentMatrix.experiment_classifiers(self.dir_id)


if __name__ == "__main__":
    projects = D4J.read_commit_db(sys.argv[1], sys.argv[2])
    projects[int(sys.argv[3])].save_traces()
    # projects[int(sys.argv[1])].labels()
    # projects[int(sys.argv[1])].save_traces()
